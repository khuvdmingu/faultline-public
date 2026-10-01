// 추적 탐색 — tension → 검색 패키지 → 유추 → principle → 미래 가정 → scenario → 평가, 그리고 원문까지.
import { esc, by, badge, highlight, agentRows } from "../util.js";

const HORIZON = { probable: "probable", plausible: "plausible", possible: "possible", preferable: "preferable", wildcard: "wildcard" };
const SCORE_KO = { behavioral_grounding: "근거", tension_strength: "tension", novelty: "새로움", cliche_level: "뻔함",
                   plausibility: "현실성", device_fit: "기기", ai_necessity: "AI", agent_fit: "에이전트" };

export function scoreChips(ev) {
  if (!ev) return "";
  return `<div class="scores">${Object.entries(ev.scores || {}).map(([k, v]) => `<span title="${esc(k)}">${esc(SCORE_KO[k] || k)} ${v === null ? "—" : v}</span>`).join("")}
    ${badge(ev.review_route || "", ev.review_route === "develop_candidate" ? "ok" : "")}</div>`;
}

export function render(app, el) {
  const D = app.state.data, labels = app.state.labels || {};
  const beh = by(D.behaviors), raw = by(D.raw), ten = by(D.tensions), ana = by(D.analogies);
  const evalOf = {}; D.evaluations.forEach(e => evalOf[e.scenario_id] = e);
  const famOf = {}; D.families.forEach(f => f.scenario_ids.forEach(s => famOf[s] = f));
  const pkgOf = {}; D.packages.forEach(p => pkgOf[p.tension_id] = p);
  const linked = new Set(); D.tensions.forEach(t => [...t.member_ids, ...t.counterexample_ids].forEach(b => linked.add(b)));
  const unl = D.behaviors.filter(b => !linked.has(b.id));
  if (!app.sel.tension || (app.sel.tension !== "_none" && !ten[app.sel.tension])) app.sel.tension = D.tensions[0] ? D.tensions[0].id : "_none";
  const cur = app.sel.tension;
  const ev = app.evaluator;

  const majority = t => { const c = {}; t.member_ids.forEach(b => { const l = beh[b] && labels[beh[b].source_id]; const k = l ? (l.tension || "무소속") : "?"; c[k] = (c[k] || 0) + 1; });
    return Object.entries(c).sort((a, b) => b[1] - a[1])[0]?.[0]; };
  const chip = (rid, expect) => { if (!ev) return ""; const L = labels[rid]; if (!L) return "";
    const ok = expect === undefined ? !L.tension : (L.tension || "무소속") === expect;
    return `<span class="badge gt ${ok ? "" : "miss"}" title="정답 라벨">${esc(L.tension || "무소속")} · ${esc(L.role)}</span>`; };
  const item = (bid, expect, reason) => { const b = beh[bid]; if (!b) return `<div class="item">${badge("없는 ID " + bid, "bad")}</div>`;
    const r = raw[b.source_id] || {}; const ctx = Object.entries(b.context || {}).filter(([, v]) => v !== null).map(([k, v]) => `${k}=${esc(v)}`).join(" · ");
    return `<div class="item"><div class="row">${badge(b.kind)}<b>${esc(b.action)}</b>${chip(b.source_id, expect)}${reason ? `<span class="tiny muted">${esc(reason)}</span>` : ""}</div>
      <div class="raw">${esc(b.id)} ← ${esc(b.source_id)} “${highlight(r.raw_text, b.source_excerpt)}”</div>
      ${ctx ? `<div class="tiny muted">context: ${ctx}</div>` : ""}${b.inferred_need ? `<div class="tiny muted">추론(${esc(b.inference_status)}): ${esc(b.inferred_need)}</div>` : ""}</div>`; };

  const nav = `<nav class="card list" aria-label="tension 목록"><h2>tension</h2>
    ${D.tensions.length ? "" : '<p class="empty small">20 연결 스테이지 결과가 아직 없다.</p>'}
    ${D.tensions.map(t => `<button data-t="${t.id}" aria-current="${t.id === cur}">${esc(t.id)} · ${esc(t.label)}<small>행동 ${t.member_ids.length} · 반례 ${t.counterexample_ids.length} · 시나리오 ${D.scenarios.filter(s => s.tension_ids.includes(t.id)).length}${ev ? " · 다수 정답 " + esc(majority(t) || "—") : ""}</small></button>`).join("")}
    <button data-t="_none" aria-current="${cur === "_none"}">연결되지 않은 행동<small>${unl.length}개 — 방해물이 여기 있어야 정상</small></button></nav>`;

  let body;
  if (cur === "_none") {
    body = `<h2>연결되지 않은 행동 (${unl.length})</h2>${unl.map(b => item(b.id)).join("") || '<p class="empty">없음</p>'}`;
  } else {
    const t = ten[cur], m = majority(t), pk = pkgOf[t.id];
    const pris = D.principles.filter(p => p.tension_ids.includes(t.id));
    const tAna = D.analogies.filter(a => a.target_tension_ids.includes(t.id));
    const prems = D.premises.filter(p => p.origin_tension_ids.includes(t.id) || p.principle_ids.some(x => pris.some(pp => pp.id === x)));
    const scns = D.scenarios.filter(s => s.tension_ids.includes(t.id));
    body = `<div class="row">${`<h2 style="margin:0">${esc(t.id)} · ${esc(t.label)}</h2>`}${ev && m ? `<span class="badge gt">다수 정답 ${esc(m)}</span>` : ""}</div>
      <div class="poles"><div class="pole">${esc(t.pole_a)}</div><div class="muted" style="text-align:center">↔</div><div class="pole">${esc(t.pole_b)}</div></div>
      ${(t.alternative_interpretations || []).length ? `<p class="small muted" style="margin-top:8px">다른 해석: ${t.alternative_interpretations.map(esc).join(" / ")}</p>` : ""}

      <h3>scenario (${scns.length})</h3>
      ${scns.map(s => `<div class="box"><div class="row between"><b>${esc(s.id)} · ${esc(s.title)}</b>
          <div class="row">${s._polished ? badge("윤문") : ""}${s.horizon ? badge(s.horizon) : ""}${famOf[s.id] ? badge(famOf[s.id].id + " " + famOf[s.id].label) : ""}${s.evidence_ids.every(e => beh[e]) ? "" : badge("추적 끊김", "bad")}</div></div>
        <dl class="kv"><dt>trigger</dt><dd>${esc(s.trigger)}</dd><dt>경험</dt><dd>${esc(s.experience)}</dd>${s.takeaway ? `<dt>핵심</dt><dd>${esc(s.takeaway)}</dd>` : ""}
          ${s.device_role ? `<dt>기기 역할</dt><dd>${esc(s.device_role)}</dd>` : ""}${agentRows(s)}
          <dt>가정</dt><dd>${(s.assumptions || []).map(esc).join("<br>") || "—"}</dd><dt>실패 장면</dt><dd>${esc(s.failure_case)}</dd>
          <dt>근거</dt><dd>${s.evidence_ids.map(e => `${esc(e)}${beh[e] ? ` “${esc(beh[e].source_excerpt)}”` : ""}`).join("<br>")}</dd>
          <dt>평가</dt><dd>${scoreChips(evalOf[s.id]) || "—"}</dd></dl></div>`).join("") || '<p class="empty small">없음</p>'}

      <h3>principle (${pris.length})</h3>
      ${pris.map(p => `<div class="item"><b>${esc(p.id)}</b> ${esc(p.statement)}${p.rationale ? `<div class="tiny muted">${esc(p.rationale)}</div>` : ""}
        ${(p.analogy_ids || []).length ? `<div class="tiny muted">활용한 유추: ${p.analogy_ids.map(esc).join(", ")}</div>` : ""}</div>`).join("") || '<p class="empty small">없음</p>'}

      <h3>미래 가정 (${prems.length})</h3>
      ${prems.map(p => `<div class="box"><div class="row">${badge(p.horizon)}<b>${esc(p.what_if)}</b></div>
        <dl class="kv"><dt>바뀐 전제</dt><dd>${esc(p.changed_assumption)}</dd><dt>미래 규칙</dt><dd>${esc(p.future_rule)}</dd>
          <dt>필요 조건</dt><dd>${(p.required_changes || []).map(esc).join("<br>")}</dd>
          <dt>수혜자</dt><dd>${(p.beneficiaries || []).map(esc).join(", ") || "—"}</dd><dt>잃는 것</dt><dd>${(p.tradeoffs || []).map(esc).join("<br>")}</dd></dl></div>`).join("") || '<p class="empty small">없음</p>'}

      <h3>먼 영역 유추 (${tAna.length})</h3>
      ${tAna.map(a => `<div class="item"><div class="row">${badge(a.distance)}<b>${esc(a.source_domain)} — ${esc(a.source_pattern)}</b></div>
        <div class="small">${esc(a.abstract_mechanism)}</div>
        <div class="tiny muted">대응: ${Object.entries(a.mapping || {}).map(([k, v]) => `${esc(k)} → ${esc(v)}`).join(" · ")}</div>
        <div class="tiny muted">전이 한계: ${(a.transfer_limitations || []).map(esc).join(" / ")}</div></div>`).join("") || '<p class="empty small">없음</p>'}

      ${pk ? `<h3>검색 패키지 ${esc(pk.id)} <span class="tiny muted">${esc(pk.retrieval_version)} · relevant ${pk.relevant_ids.length} / adjacent ${pk.adjacent_ids.length} / distant ${pk.distant_analogy_ids.length}</span></h3>
        <details><summary class="small">인접 맥락 행동 ${pk.adjacent_ids.length}개 · 먼 유추 ${pk.distant_analogy_ids.length}개 (선택 이유 포함)</summary>
          ${pk.adjacent_ids.map(b => item(b, undefined, pk.reasons && pk.reasons[b])).join("")}
          ${pk.distant_analogy_ids.map(a => ana[a] ? `<div class="item small"><b>${esc(a)}</b> ${esc(ana[a].source_domain)} — ${esc(ana[a].abstract_mechanism)} <span class="tiny muted">${esc((pk.reasons || {})[a] || "")}</span></div>` : "").join("")}
        </details>` : ""}

      <h3>행동 (${t.member_ids.length})</h3>${t.member_ids.map(b => item(b, m)).join("")}
      <h3>반례 (${t.counterexample_ids.length})</h3>${t.counterexample_ids.map(b => item(b, m)).join("") || '<p class="empty small">없음</p>'}`;
  }
  el.innerHTML = `<section class="split">${nav}<article class="card">${body}</article></section>`;
  el.querySelectorAll("[data-t]").forEach(b => b.onclick = () => { app.sel.tension = b.dataset.t; render(app, el); });
}
