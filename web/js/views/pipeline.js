// 파이프라인 — 스테이지 실행. 프론트는 요청만 보내고, 작업 생성·배치·검증·저장은 백엔드가 한다.
import { api } from "../api.js";
import { esc, badge, statusBadge, copy, store } from "../util.js";

const KIND = { human: "사람", det: "스크립트", llm: "LLM" };

function execBar(app) {
  const x = app.executors;
  if (!x) return `<div class="note">실행기 상태 확인 중…</div>`;
  const c = x.claude_cli || {};
  const pref = store("fl.executor") || (c.ok ? "claude_cli" : "manual");
  return `<div class="row between">
      <div class="row"><b>실행기</b>
        <label class="inline"><input type="radio" name="exec" value="claude_cli" ${pref === "claude_cli" ? "checked" : ""} ${c.ok ? "" : "disabled"}> 자동 (claude CLI)</label>
        <label class="inline"><input type="radio" name="exec" value="manual" ${pref !== "claude_cli" || !c.ok ? "checked" : ""}> 수동 (복사·붙여넣기)</label></div>
      <button class="btn sm" id="execCheck">상태 다시 확인</button></div>
    <div class="note ${c.ok ? "ok" : "warn"}" style="margin-top:8px">
      claude CLI: ${c.ok ? "사용 가능 — 백엔드가 직접 호출한다 (구독 사용량에서 차감, 도구 없음·워크스페이스 밖 임시 폴더에서 실행)" : esc(c.message || "사용 불가")}
      ${c.hint ? `<br>→ ${esc(c.hint)}` : ""}${(c.warnings || []).map(w => `<br>⚠ ${esc(w)}`).join("")}
      <span class="tiny muted"> · 확인 ${esc(x.checked_at || "")}</span></div>`;
}

// 전체 자동 실행 — 정답표(없을 때만)부터 후보 추리기·채점까지. 사람 검토는 그 뒤에 선택.
const STEP_BADGE = { pending: ["대기", ""], running: ["실행 중", "warn"], done: ["완료", "ok"], stopped: ["멈춤", "bad"], redo: ["다시", "warn"] };
// 서버 시각은 로컬 시간 문자열(YYYY-MM-DDTHH:MM:SS) — b 가 없으면 지금까지
const secs = (a, b) => a ? Math.max(0, ((b ? new Date(b) : new Date()) - new Date(a)) / 1000) : null;
const dur = s => s == null ? "" : s < 60 ? `${Math.round(s)}초` : `${Math.floor(s / 60)}분 ${Math.round(s % 60)}초`;
const optSel = (key, label, opts, cur) => `<label class="inline">${esc(label)} <select data-cfg="${key}" aria-label="${esc(label)}">${Object.entries(opts).map(([k, v]) => `<option value="${k}" ${k === cur ? "selected" : ""} title="${esc(v)}">${esc(v.split(" — ")[0])}</option>`).join("")}</select></label>`;
function autoCard(app) {
  const S = app.state, st = S.autorun, active = S.autorun_active, order = S.autorun_order || [];
  const byId = Object.fromEntries(app.meta.registry.stages.map(s => [s.id, s]));
  const name = id => byId[id] ? `${byId[id].num} ${byId[id].name}` : id;
  const plan = S.autorun_plan || [];
  const cli = (app.executors || {}).claude_cli || {};
  const steps = st ? `<ol class="auto-steps">${st.steps.map(x => {
      const [t, k] = STEP_BADGE[x.status] || [x.status, ""];
      const el = x.status === "pending" ? null : secs(x.started, x.finished || null);
      return `<li><span>${esc(name(x.stage))}</span> ${badge(t, k)}${el != null ? `<span class="tiny muted">${dur(el)}</span>` : ""}${x.rows != null ? `<span class="tiny muted">${x.rows}행</span>` : ""}${x.note ? `<span class="tiny muted">${esc(x.note)}</span>` : ""}${x.error ? `<div class="msg bad">${esc(x.error)}</div>` : ""}</li>`; }).join("")}</ol>` : "";
  const head = !st ? "" : `<div class="row">${badge({ running: "실행 중", done: "끝", stopped: "멈춤", interrupted: "중단됨(서버 재시작)" }[st.status] || st.status, { done: "ok", stopped: "bad", interrupted: "warn", running: "warn" }[st.status] || "")}
      <span class="tiny muted">${esc(st.started || "")}${st.finished ? " → " + esc(st.finished) : ""} · 걸린 시간 ${dur(secs(st.started, st.finished || null))}</span></div>
      ${st.error ? `<div class="msg bad">${esc(st.error)} — 원인을 고친 뒤 「이어서 실행」</div>` : ""}`;
  return `<section class="card"><div class="row between"><h2 style="margin:0">전체 자동 실행</h2>
      ${st && st.status === "done" && S.data.shortlist && S.data.shortlist.picks ? `<button class="btn sm" data-go="review">자동 후보 ${S.data.shortlist.picks.length}개 보기</button>` : ""}</div>
    <p class="small muted" style="margin:6px 0 10px">정답표(없을 때만) → 합성 생성 → … → 윤문 → <b>후보 추리기</b> → 채점까지 한 번에 돈다. 사람 검토는 끝난 뒤 원하면 한다. 각 LLM 단계는 claude CLI 로, 검증 오류가 나면 저장하지 않고 멈춘다.</p>
    ${active ? `<p class="tiny muted">크기 ${esc(S.config.label)} · 동시 배치 ${S.config.parallel}</p>` : `<div class="row" style="margin-bottom:8px">
      <b class="small">크기</b>${Object.entries(S.options.sizes).map(([k, v]) => `<label class="inline" title="${esc(v.desc)}"><input type="radio" name="size" value="${k}" ${S.config.size === k ? "checked" : ""}> ${esc(v.label)} <span class="tiny muted">${esc(v.desc)}</span></label>`).join("")}
      <label class="inline">동시 배치 <select id="par" aria-label="동시 배치 수">${[1, 2, 3, 4, 5, 6].map(n => `<option ${S.config.parallel === n ? "selected" : ""}>${n}</option>`).join("")}</select></label></div>
    <div class="row" style="margin-bottom:8px">
      ${optSel("profile", "흐름", S.options.profiles, S.config.profile)}${optSel("brevity", "길이", S.options.brevity, S.config.brevity)}
      ${optSel("polish", "윤문", S.options.polish, S.config.polish)}${optSel("family", "family", S.options.family, S.config.family)}${optSel("assign", "판단 필터 B", S.options.assign, S.config.assign)}${S.config.assign === "on" ? optSel("assign_rule", "필터 규칙", S.options.assign_rule, S.config.assign_rule) : ""}${optSel("baseline_split", "기준선", S.options.baseline_split, S.config.baseline_split)}</div>
    <p class="tiny muted" style="margin:0 0 8px">크기는 정답표·합성 원문을 새로 만들 때 적용된다. 이미 만든 정답표의 tension 수는 바뀌지 않는다 — 처음부터 다시 돌리려면 시작을 「00 정답표」로. 동시 배치를 늘리면 빨라지지만 한꺼번에 도는 claude 프로세스가 늘어난다.</p>
    <div class="row">
      <label class="inline">시작 <select id="autoFrom" aria-label="시작 스테이지"><option value="">이어서 (${plan.length ? esc(name(plan[0])) + "부터" : "모두 끝남"})</option>${order.map(id => `<option value="${id}">${esc(name(id))}</option>`).join("")}</select></label>
      <label class="inline">끝 <select id="autoTo" aria-label="끝 스테이지">${order.map(id => `<option value="${id}" ${id === "score" ? "selected" : ""}>${esc(name(id))}</option>`).join("")}</select></label>
      <button class="btn primary" id="autoStart" ${cli.ok ? "" : "disabled"}>${st ? "실행" : "자동 실행"}</button>
      ${cli.ok ? "" : `<span class="small muted">claude CLI 가 준비돼야 한다 (위 실행기 상태)</span>`}</div><div class="msg" id="autoMsg"></div>`}
    ${head}${steps}</section>`;
}

// 실행 기록 — 자동 실행이 끝날 때마다 남는 요약. 옵션을 바꿔 돌린 결과를 나란히 본다.
function historyCard(app) {
  const runs = app.state.history || [];
  if (!runs.length) return "";
  const RUN_BADGE = { done: ["끝", "ok"], stopped: ["멈춤", "bad"] };
  const n = v => v == null ? "—" : v;
  return `<section class="card"><h2>실행 기록</h2>
    <p class="tiny muted" style="margin:0 0 8px">자동 실행 한 번 = 한 줄. 글자 수는 레코드당 평균(짧게 쓰기 효과 확인용). 데이터는 덮어쓰고 이 요약만 남는다.</p>
    <div class="table-wrap"><table class="tbl"><thead><tr><th>실행</th><th>상태</th><th>시간</th><th>설정</th><th>원칙</th><th>가정</th><th>시나리오</th><th>시나리오 수</th><th>판정</th></tr></thead><tbody>
    ${runs.map(r => { const [t, k] = RUN_BADGE[r.status] || [r.status, ""], c = r.config, x = r.text || {};
      return `<tr><td class="mono tiny">${esc(r.id)}</td><td>${badge(t, k)}</td><td>${dur(r.secs)}</td>
        <td class="tiny">${esc(c.size)} · 동시 ${c.parallel} · ${esc(c.brevity)} · ${esc(c.profile)}${c.assign === "on" ? " · 필터 " + esc(c.assign_rule || "v1") : ""}${c.baseline_split && c.baseline_split !== "off" ? " · 기준선 " + esc(c.baseline_split) : ""}</td>
        <td>${n(x.principles)}</td><td>${n(x.premises)}</td><td>${n(x.scenarios)}</td><td>${n((r.counts || {}).scenarios)}</td>
        <td>${r.score ? `${r.score.pass}/${r.score.total}` : "—"}</td></tr>`; }).join("")}</tbody></table></div></section>`;
}

function newExpCard() {
  return `<section class="card"><details><summary><b>새 실험 만들기</b> <span class="small muted">— 기기·영역만 적으면 정답표부터 자동으로 만든다</span></summary>
    <div class="form-grid" style="margin-top:10px">
      <label>이름 <input id="nxName" placeholder="fridge-v1" autocomplete="off"></label>
      <label>기기 <input id="nxDevice" placeholder="패밀리허브 냉장고"></label>
      <label class="wide">탐색 영역 <input id="nxDomain" placeholder="주방에서의 식재료 관리와 가족 간 소통"></label>
      <label class="wide">기기 특성 <span class="tiny muted">(쉼표로)</span><input id="nxTraits" placeholder="큰 터치 화면, 주방에 있음, 가족이 함께 씀"></label>
      <label>크기 <select id="nxSize"><option value="quick" selected>빠르게 — tension 4 · 원문 약 45 · sonnet</option><option value="standard">표준 — tension 6 · 원문 약 100</option></select></label>
      <label>길이 <select id="nxBrev"><option value="short" selected>짧게</option><option value="normal">보통</option></select></label>
      <label>흐름 <select id="nxProf"><option value="full" selected>전 과정</option><option value="check">검증 전용 (생성·추출·연결·채점)</option></select></label>
      <label class="wide">기반 기술 <span class="tiny muted">(비우면 에이전틱 AI)</span><input id="nxTech" placeholder="에이전틱 AI — 목표를 받아 스스로 계획하고 대신 행동하며, 필요할 때만 묻는 AI"></label>
      <label>동시 배치 <select id="nxPar">${[1, 2, 3, 4, 5, 6].map(n => `<option ${n === 3 ? "selected" : ""}>${n}</option>`).join("")}</select></label>
      <label class="wide">주변 서비스 <span class="tiny muted">(쉼표로)</span><input id="nxAround" placeholder="스마트폰, 장보기 앱, 메신저"></label>
    </div>
    <p class="tiny muted">여기 적는 내용은 파이프라인이 보는 탐색 과제(brief)다. 정답 tension 은 적지 않는다.</p>
    <div class="row"><button class="btn primary sm" id="nxCreate">만들기</button><label class="inline small"><input type="checkbox" id="nxRun" checked> 만든 뒤 바로 자동 실행</label></div>
    <div class="msg" id="nxMsg"></div></details></section>`;
}

function jobCard(app, j, open) {
  const res = j.result || {};
  const batches = (j.batches || []).map(b => `<div class="batch">
      <div class="row between"><span class="small">배치 ${b.index + 1}/${j.batches.length} · 입력 ${b.items.length}개 · ${b.prompt_chars.toLocaleString()}자 ${statusBadge(b.status === "pending" ? "waiting" : b.status)}</span>
        <div class="row"><button class="btn sm" data-copy="${j.id}:${b.index}">프롬프트 복사</button><button class="btn sm" data-show="${j.id}:${b.index}">보기</button></div></div>
      ${b.error ? `<div class="msg bad">${esc(b.error)}</div>` : ""}
      <pre class="prompt" id="p-${j.id}-${b.index}" hidden></pre>
      ${j.executor === "manual" && b.status !== "done" && j.status !== "done" ? `<details style="margin-top:6px"><summary class="small muted">결과 붙여넣기</summary>
        <textarea data-ta="${j.id}:${b.index}" placeholder="모델 출력을 그대로 — 코드 펜스·설명 줄은 서버가 걸러낸다"></textarea>
        <div class="row" style="margin-top:6px"><button class="btn primary sm" data-paste="${j.id}:${b.index}">저장</button></div></details>` : ""}
    </div>`).join("");
  return `<div class="job" id="job-${j.id}">
    <div class="row between"><div class="row"><b>${esc(j.stage)}</b>${statusBadge(j.status)}${badge(j.executor === "manual" ? "수동" : "CLI")}${badge(j.model)}</div>
      <span class="tiny muted mono">${esc(j.id)}</span></div>
    ${j.error ? `<div class="msg bad">${esc(j.error)}</div>` : ""}
    ${res.rows !== undefined ? `<div class="small" style="margin-top:6px">결과 ${res.rows}행${res.file ? ` → <code>${esc(res.file)}</code>` : ""}${res.forced ? " " + badge("오류 무시하고 저장", "warn") : ""}</div>` : ""}
    ${res.error_count ? `<ul class="errs">${res.errors.map(e => `<li class="e">${esc(e)}</li>`).join("")}${res.error_count > res.errors.length ? `<li>… 외 ${res.error_count - res.errors.length}건</li>` : ""}</ul>` : ""}
    ${(res.warnings || []).length ? `<details><summary class="small muted">경고 ${res.warnings.length}</summary><ul class="errs">${res.warnings.map(e => `<li>${esc(e)}</li>`).join("")}</ul></details>` : ""}
    <div class="actions">
      ${j.status === "needs_review" ? `<button class="btn danger sm" data-force="${j.id}">오류를 알고도 저장</button><span class="tiny muted">또는 프롬프트를 고쳐 새 작업을 만든다</span>` : ""}
      ${j.status === "failed" && j.executor === "claude_cli" ? `<button class="btn sm" data-retry="${j.id}">재시도</button>` : ""}
    </div>
    <details ${open ? "open" : ""}><summary class="small muted">배치 ${j.batches.length}개</summary>${batches}</details>
  </div>`;
}

function stageRow(app, s) {
  const st = (app.state.stages || []).find(x => x.id === s.id) || {};
  const outs = (st.outputs || []).map(o => o.exists ? `${badge(o.key + " " + o.count, "ok")}` : badge(o.key + " 없음")).join(" ");
  const lj = st.last_job;
  let act = "";
  if (s.kind === "llm") {
    const hiddenNote = !s.hidden ? "" : s.id === "ground_truth" ? `<span class="tiny muted">정답표를 쓰는 단계 — 결과는 hidden/ 에만 저장되고 파이프라인은 볼 수 없다</span>`
      : `<span class="tiny muted">이 스테이지만 정답표를 읽는다 — 파이프라인과 다른 모델로</span>`;
    const mm = (app.state.config || {}).model_map || {}, dm = mm[s.model] || s.model;
    act = `<select data-model="${s.id}" aria-label="${esc(s.name)} 모델">${app.meta.models.map(m => `<option ${m === dm ? "selected" : ""}>${m}</option>`).join("")}</select>
      <button class="btn primary sm" data-job="${s.id}">작업 만들기</button><button class="btn sm" data-preview="${s.id}">프롬프트 미리보기</button>${hiddenNote}`;
    if (s.id === "ground_truth") act += `<span class="tiny muted">사람이 <code>hidden/ground_truth.json</code> 을 직접 써 두면 자동 실행은 이 단계를 건너뛴다</span>`;
  } else if (s.kind === "det" && s.id !== "score") {
    act = `<button class="btn primary sm" data-det="${s.id}">실행</button>`;
  } else if (s.id === "score") {
    act = app.evaluator ? `<button class="btn primary sm" data-score="1">채점 실행</button>` : `<span class="small muted">평가자 모드에서만 실행한다</span>`;
  } else if (s.id === "ground_truth") {
    act = `<span class="small muted"><code>hidden/ground_truth.json</code> 을 파일에서 직접 편집한다 — 작성 규칙은 문서 탭의 데이터 생성 정책 §2</span>`;
  } else if (s.id === "review") {
    act = `<button class="btn sm" data-go="review">검토 탭으로</button>`;
  }
  return `<div class="stage ${app.sel.focusStage === s.id ? "focus" : ""}" id="st-${s.id}"><div class="n">${esc(s.num)}</div><div>
    <div class="row"><b>${esc(s.name)}</b>${badge(s.kind === "llm" ? "LLM" : KIND[s.kind])}${s.optional ? badge("선택") : ""}${outs}
      ${lj ? `<span class="small muted">최근 작업</span> ${statusBadge(lj.status)}` : ""}</div>
    <div class="small muted" style="margin-top:4px">${esc(s.desc)}</div>
    <div class="actions">${act}</div><div class="msg" data-msg="${s.id}"></div>
    <pre class="prompt" id="pv-${s.id}" hidden></pre></div></div>`;
}

export function render(app, el) {
  const stages = [...app.meta.registry.stages].sort((a, b) => a.num.localeCompare(b.num));
  const v = app.state.validate;
  const openJob = app.sel.job;
  el.innerHTML = `<section class="card">${execBar(app)}</section>${autoCard(app)}${historyCard(app)}${newExpCard()}
    <section class="pipe-grid">
      <div class="card"><h2>스테이지</h2>${stages.map(s => stageRow(app, s)).join("")}</div>
      <div class="stack">
        <div class="card"><div class="row between"><h2 style="margin:0">작업</h2><button class="btn sm" id="reload">새로고침</button></div>
          ${app.jobs.length ? app.jobs.slice(0, 15).map(j => jobCard(app, j, j.id === openJob || ["waiting", "needs_review"].includes(j.status))).join("") : '<p class="empty small">아직 작업이 없다. 왼쪽에서 LLM 스테이지의 「작업 만들기」를 누른다.</p>'}</div>
        <div class="card"><h2>검증</h2>${!v ? '<p class="muted small">raw 가 생기면 검사한다.</p>' :
          `<div class="row">${v.errors.length ? badge("오류 " + v.errors.length, "bad") : badge("오류 0", "ok")}${badge("경고 " + v.warnings.length, v.warnings.length ? "warn" : "")}</div>
           <p class="tiny muted" style="margin-top:6px">${Object.entries(v.counts).map(([k, n]) => `${k} ${n}`).join(" · ")}${v.skipped.length ? " · 미생성: " + v.skipped.join(", ") : ""}</p>
           ${v.errors.length || v.warnings.length ? `<ul class="errs">${v.errors.slice(0, 30).map(e => `<li class="e">${esc(e)}</li>`).join("")}${v.warnings.slice(0, 20).map(e => `<li>${esc(e)}</li>`).join("")}</ul>` : ""}`}</div>
      </div></section>`;
  bind(app, el);
  if (app.sel.focusStage) { const n = document.getElementById("st-" + app.sel.focusStage); if (n) n.scrollIntoView({ block: "center" }); app.sel.focusStage = null; }
}

function msg(el, id, ok, html) { const m = el.querySelector(`[data-msg="${id}"]`); if (m) { m.className = "msg " + (ok ? "ok" : "bad"); m.innerHTML = html; } }
const errText = e => esc(e.message) + (e.data && (e.data.errors || e.data.details) ? `<ul class="errs">${(e.data.errors || e.data.details).map(x => `<li>${esc(x)}</li>`).join("")}</ul>` : "");

function bind(app, el) {
  const exec = () => (el.querySelector('input[name="exec"]:checked') || {}).value || "manual";
  el.querySelectorAll('input[name="exec"]').forEach(r => r.onchange = () => store("fl.executor", r.value));
  const chk = el.querySelector("#execCheck");
  if (chk) chk.onclick = async () => { chk.disabled = true; chk.textContent = "확인 중…"; app.executors = await api.executors(true).catch(e => ({ claude_cli: { ok: false, message: e.message } })); app.rerender(); };
  el.querySelector("#reload").onclick = () => app.refresh();

  const saveCfg = async () => {
    const size = (el.querySelector('input[name="size"]:checked') || {}).value, par = el.querySelector("#par");
    const body = { size, parallel: par ? Number(par.value) : undefined };
    el.querySelectorAll("[data-cfg]").forEach(x => body[x.dataset.cfg] = x.value);
    try { await api.setConfig(app.root, body); await app.refresh(); }
    catch (e) { app.toast(el.querySelector("#autoMsg"), false, errText(e)); }
  };
  el.querySelectorAll('input[name="size"]').forEach(r => r.onchange = saveCfg);
  const par = el.querySelector("#par"); if (par) par.onchange = saveCfg;
  el.querySelectorAll("[data-cfg]").forEach(x => x.onchange = saveCfg);
  const start = el.querySelector("#autoStart");
  if (start) start.onclick = async () => {
    start.disabled = true;
    try { await api.autorun(app.root, el.querySelector("#autoFrom").value, el.querySelector("#autoTo").value); await app.refresh(); }
    catch (e) { app.toast(el.querySelector("#autoMsg"), false, errText(e)); start.disabled = false; }
  };
  const mk = el.querySelector("#nxCreate");
  if (mk) mk.onclick = async () => {
    const v = id => el.querySelector(id).value.trim(), out = el.querySelector("#nxMsg");
    mk.disabled = true;
    try {
      const r = await api.newExperiment({ name: v("#nxName"), device: v("#nxDevice"), domain: v("#nxDomain"),
                                          device_traits: v("#nxTraits"), surroundings: v("#nxAround"),
                                          size: v("#nxSize"), parallel: Number(v("#nxPar")), brevity: v("#nxBrev"),
                                          profile: v("#nxProf"), technology: v("#nxTech") });
      const run = el.querySelector("#nxRun").checked;
      await app.reloadMeta(r.root);
      if (run) { await api.autorun(r.root); await app.refresh(); }
    } catch (e) { app.toast(out, false, errText(e)); mk.disabled = false; }
  };

  el.querySelectorAll("[data-job]").forEach(b => b.onclick = async () => {
    const sid = b.dataset.job, model = el.querySelector(`[data-model="${sid}"]`).value;
    b.disabled = true;
    try { const j = await api.createJob(app.root, sid, exec(), model); app.sel.job = j.id; await app.refresh(); }
    catch (e) { msg(el, sid, false, errText(e)); b.disabled = false; }
  });
  el.querySelectorAll("[data-preview]").forEach(b => b.onclick = async () => {
    const sid = b.dataset.preview, pre = el.querySelector("#pv-" + sid);
    if (!pre.hidden) { pre.hidden = true; return; }
    try { const p = await api.preview(app.root, sid); pre.textContent = `[배치 ${p.batches.length}개 · ${p.batches.map(x => x.chars.toLocaleString() + "자").join(", ")}]\n\n` + p.first; pre.hidden = false; }
    catch (e) { msg(el, sid, false, errText(e)); }
  });
  el.querySelectorAll("[data-det]").forEach(b => b.onclick = async () => {
    const sid = b.dataset.det; b.disabled = true;
    try {
      const r = await api.runDet(app.root, sid);
      await app.refresh();
      const extra = r.qa ? ` · 데이터 품질: <b>${esc(r.qa.verdict)}</b> (FAIL ${r.qa.fail} · 주의 ${r.qa.warn}) — 평가자 모드의 채점·품질 탭에서 확인` : "";
      msg(document, sid, true, sid === "split" ? `원문 ${r.raw_count}개 분리${extra}` : sid === "shortlist" ? `후보 ${r.picks.length}개 (적격 ${r.counts.eligible})` : `패키지 ${r.count}개`);
    } catch (e) { msg(el, sid, false, errText(e)); b.disabled = false; }
  });
  el.querySelectorAll("[data-score]").forEach(b => b.onclick = async () => {
    try { await api.score(app.root); app.go("score"); } catch (e) { msg(el, "score", false, errText(e)); }
  });
  el.querySelectorAll("[data-go]").forEach(b => b.onclick = () => app.go(b.dataset.go));

  el.querySelectorAll("[data-copy]").forEach(b => b.onclick = async () => {
    const [id, i] = b.dataset.copy.split(":");
    const { text } = await api.jobPrompt(app.root, id, i);
    b.textContent = (await copy(text)) ? "복사됨 ✓" : "복사 실패 — 보기에서 선택";
  });
  el.querySelectorAll("[data-show]").forEach(b => b.onclick = async () => {
    const [id, i] = b.dataset.show.split(":"), pre = el.querySelector(`#p-${id}-${i}`);
    if (!pre.hidden) { pre.hidden = true; return; }
    pre.textContent = (await api.jobPrompt(app.root, id, i)).text; pre.hidden = false;
  });
  el.querySelectorAll("[data-paste]").forEach(b => b.onclick = async () => {
    const [id, i] = b.dataset.paste.split(":"), ta = el.querySelector(`[data-ta="${id}:${i}"]`);
    b.disabled = true;
    try { await api.paste(app.root, id, i, ta.value); app.sel.job = id; await app.refresh(); }
    catch (e) {
      if (e.data && e.data.job) { app.sel.job = id; await app.refresh(); return; }
      ta.insertAdjacentHTML("afterend", `<div class="msg bad">${errText(e)}</div>`); b.disabled = false;
    }
  });
  el.querySelectorAll("[data-force]").forEach(b => b.onclick = async () => {
    if (!confirm("검증 오류가 있는 결과를 저장한다. 뒤 스테이지가 끊긴 참조를 만나게 된다. 계속할까?")) return;
    try { await api.finalize(app.root, b.dataset.force, true); } catch (e) {} await app.refresh();
  });
  el.querySelectorAll("[data-retry]").forEach(b => b.onclick = async () => { await api.retry(app.root, b.dataset.retry); await app.refresh(); });
}
