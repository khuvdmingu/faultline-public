// 인간 검토 — 설계 §22.3: 시나리오 설명만 먼저 보고 판단(블라인드), 근거는 두 번째. 이유는 필수.
import { api } from "../api.js";
import { esc, by, badge, highlight, hash01, store, pct, agentRows } from "../util.js";
import { scoreChips } from "./explore.js";

const DEC = { develop: "발전", hold: "보류", reject: "거절" };

export function render(app, el) {
  const D = app.state.data, H = app.state.health;
  const beh = by(D.behaviors), raw = by(D.raw);
  const ev = {}; D.evaluations.forEach(e => ev[e.scenario_id] = e);
  const famOf = {}; D.families.forEach(f => f.scenario_ids.forEach(s => famOf[s] = f));
  const latest = {}; D.decisions.forEach(d => latest[d.scenario_id] = d);
  const blind = store("fl.blind") !== "0";
  // 블라인드 순서: 실험별 고정 난수 순 — 생성 순서(=조건·principle 순)가 판단에 새지 않게
  const order = [...D.scenarios].sort((a, b) => hash01(app.root + a.id) - hash01(app.root + b.id));
  const todo = order.filter(s => !latest[s.id]);
  let cur = D.scenarios.find(s => s.id === app.sel.reviewId) || todo[0];
  const saw = app.sel.sawEvidence === (cur && cur.id);
  const counts = { develop: 0, hold: 0, reject: 0 }; Object.values(latest).forEach(d => counts[d.decision]++);

  const card = cur ? `<div class="review-card">
      <div class="row between"><span class="small muted">${blind ? "블라인드 · " : ""}${todo.includes(cur) ? `남은 ${todo.length}개 중` : "다시 검토"}</span>
        ${blind ? "" : `<div class="row">${cur.horizon ? badge(cur.horizon) : ""}${famOf[cur.id] ? badge(famOf[cur.id].label) : ""}</div>`}</div>
      <h2 style="margin:8px 0">${esc(blind ? "" : cur.id + " · ")}${esc(cur.title)}</h2>
      <dl class="kv"><dt>언제</dt><dd>${esc(cur.trigger)}</dd><dt>경험</dt><dd>${esc(cur.experience)}</dd>${cur.takeaway ? `<dt>핵심</dt><dd>${esc(cur.takeaway)}</dd>` : ""}
        ${cur.device_role ? `<dt>기기 역할</dt><dd>${esc(cur.device_role)}</dd>` : ""}${agentRows(cur)}
        <dt>가정</dt><dd>${(cur.assumptions || []).map(esc).join("<br>") || "—"}</dd><dt>실패 장면</dt><dd>${esc(cur.failure_case)}</dd>
        ${blind ? "" : `<dt>평가</dt><dd>${scoreChips(ev[cur.id]) || "—"}</dd>`}</dl>
      ${saw ? `<div class="box"><b class="small">근거 (${cur.evidence_ids.length})</b>${cur.evidence_ids.map(e => beh[e] ? `<div class="item small">${esc(beh[e].action)}<div class="raw">“${highlight((raw[beh[e].source_id] || {}).raw_text, beh[e].source_excerpt)}”</div></div>` : `<div class="item">${badge("없는 근거 " + e, "bad")}</div>`).join("")}</div>`
        : `<div class="actions"><button class="btn sm" id="showEv">근거 보기 (두 번째 판단)</button><span class="tiny muted">먼저 설명만 보고 판단한 뒤 여는 것을 권한다</span></div>`}
      <h3>결정</h3>
      <div class="decide">${Object.entries(DEC).map(([k, v]) => `<button class="btn" data-dec="${k}" aria-pressed="false">${v}</button>`).join("")}</div>
      <textarea class="prose" id="reason" placeholder="이유 (필수) — 무엇이 새롭거나, 왜 버리는가. 버린 이유도 지식이다." style="margin-top:8px"></textarea>
      <div class="actions"><button class="btn primary" id="save" disabled>저장하고 다음</button>${todo.length > 1 ? `<button class="btn" id="skip">건너뛰기</button>` : ""}</div>
      <div class="msg" id="rmsg"></div></div>` : `<p class="empty">${D.scenarios.length ? "모든 시나리오를 검토했다." : "40 scenario 결과가 있어야 검토할 수 있다."}</p>`;

  const SL = D.shortlist && D.shortlist.picks ? D.shortlist : null;
  const scnBy = by(D.scenarios);
  const slCard = !SL ? `<div class="card"><h2>자동 후보</h2><p class="empty small">75 후보 추리기 결과가 없다 — 파이프라인 탭의 전체 자동 실행이 만든다.</p></div>`
    : blind ? `<div class="card"><h2>자동 후보 ${SL.picks.length}</h2><p class="small muted">블라인드 중에는 숨긴다 — 자동 순위가 판단에 새지 않게. 블라인드를 끄면 보인다.</p></div>`
    : `<div class="card"><h2>자동 후보 ${SL.picks.length}</h2>
        <ol class="picks">${SL.picks.map(p => `<li><button class="linkish" data-r="${p.scenario_id}"><b>${p.rank}. ${esc((scnBy[p.scenario_id] || {}).title || p.scenario_id)}</b></button>
          <span class="tiny muted">${esc(p.scenario_id)} · 점수 ${p.score} · ${esc(p.why.join(" · "))}${latest[p.scenario_id] ? " · 검토함: " + esc(DEC[latest[p.scenario_id].decision]) : ""}</span></li>`).join("")}</ol>
        <p class="tiny muted" style="margin-top:8px">${esc(SL.rule)} · 제외 ${SL.counts.excluded}</p></div>`;
  el.innerHTML = `<section class="split">
    <div class="stack">
      ${slCard}
      <div class="card"><h2>진행 <span class="small muted">(사람 검토는 선택)</span></h2>
        <div class="row">${badge("검토 " + Object.keys(latest).length + " / " + D.scenarios.length, "solid")}${Object.entries(counts).map(([k, n]) => badge(DEC[k] + " " + n, k === "develop" ? "ok" : "")).join("")}</div>
        ${H ? `<table style="margin-top:10px"><tr><td>발전 수율</td><td class="num">${pct(H.development_yield)}</td></tr>
          <tr><td>발전한 독립 family 수율</td><td class="num">${pct(H.distinct_family_yield)}</td></tr>
          <tr><td>발전한 family</td><td class="small">${H.developed_families.map(esc).join(", ") || "—"}</td></tr></table>
          <p class="tiny muted">설계 §23.2 — 같은 좋은 아이디어의 반복을 한 번으로 센다.</p>` : ""}
        <label class="inline" style="margin-top:8px"><input type="checkbox" id="blind" ${blind ? "checked" : ""}> 블라인드 (ID·평가·family·horizon 숨김, 무작위 순서)</label>
      </div>
      <div class="card list"><h2>검토한 것</h2>${D.scenarios.filter(s => latest[s.id]).map(s => `<button data-r="${s.id}" aria-current="${cur && cur.id === s.id}">${badge(DEC[latest[s.id].decision], latest[s.id].decision === "develop" ? "ok" : "")} ${esc(blind ? s.title : s.id + " " + s.title)}<small>${esc(latest[s.id].reason)}</small></button>`).join("") || '<p class="empty small">아직 없다.</p>'}</div>
    </div>
    <div class="card">${card}</div></section>`;

  const b = el.querySelector("#blind"); b.onchange = () => { store("fl.blind", b.checked ? "1" : "0"); render(app, el); };
  el.querySelectorAll("[data-r]").forEach(x => x.onclick = () => { app.sel.reviewId = x.dataset.r; render(app, el); });
  if (!cur) return;
  const se = el.querySelector("#showEv"); if (se) se.onclick = () => { app.sel.sawEvidence = cur.id; render(app, el); };
  let choice = null;
  const save = el.querySelector("#save"), reason = el.querySelector("#reason");
  const upd = () => save.disabled = !(choice && reason.value.trim());
  el.querySelectorAll("[data-dec]").forEach(x => x.onclick = () => { choice = x.dataset.dec; el.querySelectorAll("[data-dec]").forEach(y => y.setAttribute("aria-pressed", y === x)); upd(); });
  reason.oninput = upd;
  save.onclick = async () => {
    save.disabled = true;
    try {
      await api.review(app.root, { scenario_id: cur.id, decision: choice, reason: reason.value, blind, saw_evidence: saw });
      app.sel.reviewId = null; app.sel.sawEvidence = null; await app.refresh();
    } catch (e) { el.querySelector("#rmsg").className = "msg bad"; el.querySelector("#rmsg").textContent = e.message; save.disabled = false; }
  };
  const sk = el.querySelector("#skip");
  if (sk) sk.onclick = () => { const i = todo.indexOf(cur); app.sel.reviewId = todo[(i + 1) % todo.length].id; app.sel.sawEvidence = null; render(app, el); };
}
