// 시나리오 지도 — 근거(x) × 새로움(y). 설계 §18.4: 총점 대신 두 축으로 펼쳐 "의미 있는 예외"를 사람이 찾게 한다.
// 색 = horizon 3분류 (산점도는 범주 3색 상한 — dataviz 팔레트 1~3, all-pairs 검증 통과) + 모양으로 이중 부호화.
import { esc, by, badge, hash01 } from "../util.js";
import { scoreChips } from "./explore.js";

const W = 720, H = 460, M = { l: 56, r: 24, t: 22, b: 52 };
const CLASSES = [
  { id: "s1", name: "현재형 (probable·plausible)", test: h => !h || h === "probable" || h === "plausible", shape: "circle" },
  { id: "s2", name: "조건부 미래 (possible·preferable)", test: h => h === "possible" || h === "preferable", shape: "square" },
  { id: "s3", name: "wildcard", test: h => h === "wildcard", shape: "diamond" },
];
const cls = h => CLASSES.find(c => c.test(h)) || CLASSES[0];
const X = v => M.l + (v - 0.5) / 5 * (W - M.l - M.r);
const Y = v => H - M.b - (v - 0.5) / 5 * (H - M.t - M.b);

function shape(c, x, y, r, klass, id) {
  if (c.shape === "square") return `<rect class="${klass}" data-id="${id}" x="${x - r}" y="${y - r}" width="${2 * r}" height="${2 * r}" rx="2"/>`;
  if (c.shape === "diamond") return `<path class="${klass}" data-id="${id}" d="M${x} ${y - r - 1.5}L${x + r + 1.5} ${y}L${x} ${y + r + 1.5}L${x - r - 1.5} ${y}Z"/>`;
  return `<circle class="${klass}" data-id="${id}" cx="${x}" cy="${y}" r="${r}"/>`;
}
function legendIcon(c) {
  const k = `mk ${c.id}`;
  return `<svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true" class="map">${shape(c, 7, 7, 5, k, "")}</svg>`;
}

export function render(app, el) {
  const D = app.state.data;
  const ev = {}; D.evaluations.forEach(e => ev[e.scenario_id] = e);
  const famOf = {}; D.families.forEach(f => f.scenario_ids.forEach(s => famOf[s] = f));
  const dec = {}; D.decisions.forEach(d => dec[d.scenario_id] = d);
  const f = app.sel.mapFilter || { family: "", route: "" };
  const pts = [], nulls = [];
  D.scenarios.forEach(s => {
    const e = ev[s.id], g = e && e.scores.behavioral_grounding, n = e && e.scores.novelty;
    if (g == null || n == null) { nulls.push(s); return; }
    pts.push({ s, e, g, n, c: cls(s.horizon), fam: famOf[s.id] });
  });
  // 같은 점수 칸에 여러 개가 겹칠 때만 칸 중심 둘레에 벌려 놓는다 (순서는 ID 해시로 고정)
  const cells = {};
  pts.forEach(p => (cells[p.g + "," + p.n] = cells[p.g + "," + p.n] || []).push(p));
  Object.values(cells).forEach(group => {
    group.sort((a, b) => hash01(a.s.id) - hash01(b.s.id));
    group.forEach((p, i) => {
      const r = group.length > 1 ? Math.min(0.3, 0.1 + 0.03 * group.length) : 0, a = (2 * Math.PI * i) / group.length - Math.PI / 2;
      p.x = X(p.g + r * Math.cos(a)); p.y = Y(p.n + r * Math.sin(a));
    });
  });
  const dimmed = p => (f.family && (!p.fam || p.fam.id !== f.family)) || (f.route && p.e.review_route !== f.route);
  const routes = [...new Set(D.evaluations.map(e => e.review_route))].filter(Boolean);

  let grid = "";
  for (let v = 1; v <= 5; v++) {
    grid += `<line class="grid" x1="${X(v)}" y1="${M.t}" x2="${X(v)}" y2="${H - M.b}"/><line class="grid" x1="${M.l}" y1="${Y(v)}" x2="${W - M.r}" y2="${Y(v)}"/>
      <text class="axis-t" x="${X(v)}" y="${H - M.b + 18}" text-anchor="middle">${v}</text><text class="axis-t" x="${M.l - 12}" y="${Y(v) + 4}" text-anchor="end">${v}</text>`;
  }
  const q = (x, y, t, anchor) => `<text class="quad-t" x="${x}" y="${y}" text-anchor="${anchor}">${esc(t)}</text>`;
  const quads = q(W - M.r - 6, M.t + 14, "적극 검토 — 근거·새로움 모두 높음", "end") + q(M.l + 6, M.t + 14, "사변적 질문 후보 — 새롭지만 근거 약함", "start") +
    q(W - M.r - 6, H - M.b - 8, "개선·실행 후보 — 근거는 높고 새로움 낮음", "end") + q(M.l + 6, H - M.b - 8, "우선순위 낮음", "start");
  const marks = pts.map(p => shape(p.c, p.x, p.y, 6, `mk ${p.c.id} ${dimmed(p) ? "dim" : ""} ${app.sel.scenario === p.s.id ? "sel" : ""}`, p.s.id)).join("");
  const hits = pts.map(p => `<circle class="hit" data-id="${p.s.id}" cx="${p.x}" cy="${p.y}" r="13"><title>${esc(p.s.title)}</title></circle>`).join("");

  const sel = D.scenarios.find(s => s.id === app.sel.scenario);
  const fams = D.families.map(fa => ({ ...fa, dev: fa.scenario_ids.filter(s => dec[s] && dec[s].decision === "develop").length }));

  el.innerHTML = `<section class="card">
    <div class="row between"><h2 style="margin:0">시나리오 지도 — 근거 × 새로움</h2>
      <div class="row"><label class="inline">family <select id="fFam"><option value="">전체</option>${D.families.map(x => `<option value="${x.id}" ${f.family === x.id ? "selected" : ""}>${esc(x.id)} ${esc(x.label)}</option>`).join("")}</select></label>
        <label class="inline">평가 경로 <select id="fRoute"><option value="">전체</option>${routes.map(r => `<option ${f.route === r ? "selected" : ""}>${esc(r)}</option>`).join("")}</select></label></div></div>
    ${pts.length ? `<div class="viz" id="viz"><svg class="map" viewBox="0 0 ${W} ${H}" role="img" aria-label="시나리오 ${pts.length}개의 근거 대 새로움 산점도">
        ${grid}<line class="grid" x1="${X(3.5)}" y1="${M.t}" x2="${X(3.5)}" y2="${H - M.b}" stroke-dasharray="4 4"/><line class="grid" x1="${M.l}" y1="${Y(3.5)}" x2="${W - M.r}" y2="${Y(3.5)}" stroke-dasharray="4 4"/>
        ${quads}<text class="axis-t" x="${(M.l + W - M.r) / 2}" y="${H - 12}" text-anchor="middle">behavioral_grounding (1~5)</text>
        <text class="axis-t" transform="translate(16 ${(M.t + H - M.b) / 2}) rotate(-90)" text-anchor="middle">novelty (1~5)</text>
        ${marks}${hits}</svg><div class="tip" id="tip" hidden></div></div>
      <div class="legend">${CLASSES.map(c => `<span>${legendIcon(c)}${esc(c.name)} ${pts.filter(p => p.c.id === c.id).length}</span>`).join("")}
        <span>같은 점수의 시나리오가 여럿이면 그 칸 둘레에 벌려 놓았다</span></div>` :
      '<p class="empty">평가(50 judge) 결과가 있어야 지도를 그린다.</p>'}
    ${nulls.length ? `<p class="small muted" style="margin-top:8px">근거 또는 새로움이 판정 불가(null)거나 평가가 없는 시나리오 ${nulls.length}개는 지도에서 뺐다: ${nulls.map(s => esc(s.id)).join(", ")}</p>` : ""}
  </section>
  ${sel ? `<section class="card"><div class="row between"><h2 style="margin:0">${esc(sel.id)} · ${esc(sel.title)}</h2><button class="btn sm" id="toReview">검토하기</button></div>
     <dl class="kv"><dt>trigger</dt><dd>${esc(sel.trigger)}</dd><dt>경험</dt><dd>${esc(sel.experience)}</dd>${sel.takeaway ? `<dt>핵심</dt><dd>${esc(sel.takeaway)}</dd>` : ""}<dt>실패 장면</dt><dd>${esc(sel.failure_case)}</dd>
       <dt>family</dt><dd>${famOf[sel.id] ? esc(famOf[sel.id].label) + ` <span class="tiny muted">${esc(famOf[sel.id].mechanism)}</span>` : "—"}</dd>
       <dt>평가</dt><dd>${scoreChips(ev[sel.id]) || "—"}</dd>
       <dt>평가 이유</dt><dd class="small">${ev[sel.id] ? Object.entries(ev[sel.id].rationale || {}).map(([k, v]) => `<b>${esc(k)}</b> ${esc(v)}`).join("<br>") : "—"}</dd>
       <dt>검토</dt><dd>${dec[sel.id] ? badge(dec[sel.id].decision) + " " + esc(dec[sel.id].reason) : "아직 없음"}</dd></dl></section>` : ""}
  <section class="card"><h2>family (${fams.length})</h2><div class="grid2">
    ${fams.map(fa => `<div class="card flat"><div class="row between"><b>${esc(fa.id)} · ${esc(fa.label)}</b>${badge(fa.scenario_ids.length + "개")}</div>
      <p class="small" style="margin-top:6px">${esc(fa.mechanism)}</p>${fa.distinct_from ? `<p class="tiny muted">${esc(fa.distinct_from)}</p>` : ""}
      ${fa.variants && Object.keys(fa.variants).length ? `<ul class="tiny" style="margin:6px 0 0;padding-left:16px">${fa.scenario_ids.map(id => `<li><b>${esc(id)}</b> ${esc(fa.variants[id] || "")}</li>`).join("")}</ul>${fa.dev ? `<div class="tiny muted">발전 선택 ${fa.dev}개</div>` : ""}`
        : `<div class="tiny muted">${fa.dev ? `발전 선택 ${fa.dev}개 · ` : ""}${fa.scenario_ids.map(esc).join(", ")}</div>`}</div>`).join("") || '<p class="empty small">60 family 결과가 없다.</p>'}</div></section>
  <section class="card"><details><summary><b>표 보기</b></summary><div class="scroll" style="margin-top:8px"><table>
    <thead><tr><th>시나리오</th><th class="num">근거</th><th class="num">새로움</th><th class="num">뻔함</th><th>horizon</th><th>경로</th><th>family</th></tr></thead><tbody>
    ${D.scenarios.map(s => { const e = ev[s.id] || { scores: {} }; return `<tr><td>${esc(s.id)} ${esc(s.title)}</td><td class="num">${e.scores.behavioral_grounding ?? "—"}</td><td class="num">${e.scores.novelty ?? "—"}</td>
      <td class="num">${e.scores.cliche_level ?? "—"}</td><td class="small">${esc(s.horizon || "")}</td><td class="small">${esc(e.review_route || "")}</td><td class="small">${esc(famOf[s.id] ? famOf[s.id].id : "")}</td></tr>`; }).join("")}
    </tbody></table></div></details></section>`;

  const setF = () => { app.sel.mapFilter = { family: el.querySelector("#fFam").value, route: el.querySelector("#fRoute").value }; render(app, el); };
  el.querySelector("#fFam").onchange = setF; el.querySelector("#fRoute").onchange = setF;
  const tip = el.querySelector("#tip"), viz = el.querySelector("#viz"), P = by(pts.map(p => ({ id: p.s.id, ...p })));
  el.querySelectorAll(".hit").forEach(h => {
    h.onmouseenter = () => { const p = P[h.dataset.id]; if (!p) return;
      tip.innerHTML = `<b>${esc(p.s.id)} · ${esc(p.s.title)}</b>근거 ${p.g} · 새로움 ${p.n} · 뻔함 ${p.e.scores.cliche_level ?? "—"}<br>${esc(p.s.horizon || "")} · ${esc(p.e.review_route)}${p.fam ? "<br>" + esc(p.fam.label) : ""}`;
      const box = viz.getBoundingClientRect(), s = box.width / W;
      tip.style.left = Math.min(p.x * s + 14, box.width - 290) + "px"; tip.style.top = (p.y * s - 10) + "px"; tip.hidden = false; };
    h.onmouseleave = () => tip.hidden = true;
    h.onclick = () => { app.sel.scenario = h.dataset.id; render(app, el); };
  });
  const tr = el.querySelector("#toReview"); if (tr) tr.onclick = () => app.go("review", { reviewId: app.sel.scenario });
}
