// 앱 셸 — 탭, 실험 선택, 평가자 모드, 상태 새로고침·폴링.
import { api } from "./api.js";
import { $, esc, store } from "./util.js";
import * as overview from "./views/overview.js";
import * as pipeline from "./views/pipeline.js";
import * as explore from "./views/explore.js";
import * as map from "./views/map.js";
import * as review from "./views/review.js";
import * as coverage from "./views/coverage.js";
import * as score from "./views/score.js";
import * as docs from "./views/docs.js";

const VIEWS = [
  ["overview", "구조도", overview], ["pipeline", "파이프라인", pipeline], ["explore", "추적 탐색", explore],
  ["map", "시나리오 지도", map], ["review", "후보·검토", review], ["coverage", "커버리지", coverage],
  ["score", "채점·품질", score], ["docs", "문서", docs],
];

export const app = {
  meta: null, root: null, evaluator: false, polish: true, state: null, jobs: [], executors: null, tab: "overview",
  sel: {}, busy: false,
  rerender() { renderTabs(); render(); },
  async refresh() {
    if (!this.root) return;
    const [st, js] = await Promise.all([api.state(this.root, this.evaluator), api.jobs(this.root)]);
    applyPolish(st, this.polish);
    this.state = st; this.jobs = js.jobs;
    $("#polishWrap").hidden = !st.polishCount;
    $("#synthBadge").hidden = !st.synthetic;
    renderTabs(); render();
    schedule();
  },
  async reloadMeta(select) {
    this.meta = await api.meta();
    if (select) { this.root = select; store("fl.root", select); this.sel = {}; }
    $("#root").innerHTML = this.meta.roots.map(r => `<option ${r === this.root ? "selected" : ""}>${esc(r)}</option>`).join("");
    await this.refresh();
  },
  go(tab, sel = {}) { this.tab = tab; Object.assign(this.sel, sel); store("fl.tab", tab); renderTabs(); render(); window.scrollTo(0, 0); },
  toast(el, ok, text) { if (!el) return; el.className = "msg " + (ok ? "ok" : "bad"); el.innerHTML = text; },
};

// 70 윤문 — 게이트를 통과한 윤문본을 원본 위에 덮어 보여준다. 원본 레코드·ID·참조는 그대로다.
function applyPolish(st, on) {
  const D = st.data, ov = {};
  (D.polished || []).forEach(p => { if (p.status === "accepted" || p.status === "warned") ov[p.target_id] = p.fields || {}; });
  st.polishCount = Object.keys(ov).length;
  if (!on || !st.polishCount) return;
  for (const k of ["scenarios", "principles", "premises"])
    D[k] = (D[k] || []).map(x => ov[x.id] ? Object.assign({}, x, ov[x.id], { _polished: true }) : x);
}

let timer = null;
function schedule() {
  clearTimeout(timer);
  const active = app.jobs.some(j => j.status === "queued" || j.status === "running") || (app.state && app.state.autorun_active);
  if (active) timer = setTimeout(() => { if (!document.hidden) app.refresh().catch(showError); else schedule(); }, 2500);
}

function counts() {
  const d = app.state ? app.state.data : {};
  const pending = (d.scenarios || []).filter(s => !(d.decisions || []).some(x => x.scenario_id === s.id)).length;
  return { pipeline: app.jobs.filter(j => ["queued", "running", "waiting", "needs_review"].includes(j.status)).length || "",
           review: pending || "", map: (d.scenarios || []).length || "" };
}

function renderTabs() {
  const c = counts();
  $("#tabs").innerHTML = VIEWS.map(([id, name]) =>
    `<button role="tab" data-tab="${id}" aria-selected="${id === app.tab}">${esc(name)}${c[id] ? `<span class="count">${c[id]}</span>` : ""}</button>`).join("");
  $("#tabs").querySelectorAll("button").forEach(b => b.onclick = () => app.go(b.dataset.tab));
}

function render() {
  const main = $("#main");
  const v = VIEWS.find(x => x[0] === app.tab) || VIEWS[0];
  try { Promise.resolve(v[2].render(app, main)).catch(showError); } catch (e) { showError(e); }
}

function showError(e) {
  console.error(e);
  $("#main").insertAdjacentHTML("afterbegin", `<div class="note bad">${esc(e.message || e)}</div>`);
}

(async () => {
  try {
    app.meta = await api.meta();
    const roots = app.meta.roots;
    const saved = store("fl.root");
    app.root = roots.includes(saved) ? saved : roots[0];
    app.tab = VIEWS.some(v => v[0] === store("fl.tab")) ? store("fl.tab") : "overview";
    $("#root").innerHTML = roots.map(r => `<option ${r === app.root ? "selected" : ""}>${esc(r)}</option>`).join("");
    $("#root").onchange = e => { app.root = e.target.value; app.sel = {}; store("fl.root", app.root); app.refresh().catch(showError); };
    app.polish = store("fl.polish") !== "0";
    $("#polish").checked = app.polish;
    $("#polish").onchange = e => { app.polish = e.target.checked; store("fl.polish", app.polish ? "1" : "0"); app.refresh().catch(showError); };
    $("#evaluator").onchange = e => { app.evaluator = e.target.checked; app.refresh().catch(showError); };
    renderTabs();
    await app.refresh();
    api.executors().then(x => { app.executors = x; if (app.tab === "pipeline") render(); }).catch(() => {});
  } catch (e) { showError(e); }
})();

export { render };
