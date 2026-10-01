// 구조도 — 백엔드 스테이지 등록부(engine/registry.py)에서 그린다. 코드와 그림이 어긋나지 않는다.
import { esc, badge, statusBadge } from "../util.js";

const LABEL_W = 150, COL_W = 150, NODE_W = 132, NODE_H = 60, ROW_H = 94, TOP = 16, COLS = 9;
const KIND = { human: "사람", det: "스크립트", llm: "LLM" };
const EDGE_LABEL = { "split>extract": "라벨 뗀 원문만", "link>score": "채점 대상", "split>score": "정답 라벨", "baseline>judge": "비교 기준" };

function geo(stage) {
  const [row, col] = stage.pos;
  return { x: LABEL_W + col * COL_W + (COL_W - NODE_W) / 2, y: TOP + row * ROW_H + (ROW_H - NODE_H) / 2, w: NODE_W, h: NODE_H, row, col };
}

function stageStatus(app, id) {
  const st = (app.state && app.state.stages || []).find(s => s.id === id);
  if (!st) return "";
  const lj = st.last_job;
  if (lj && ["queued", "running"].includes(lj.status)) return "running";
  if (lj && ["failed", "needs_review"].includes(lj.status) && !st.done) return "failed";
  return st.done ? "done" : "";
}

function wrap(name) {
  if (name.length <= 9) return [name];
  const i = name.indexOf(" · ");
  if (i > 0) return [name.slice(0, i), name.slice(i + 3)];
  const sp = name.lastIndexOf(" ", 9);
  return sp > 0 ? [name.slice(0, sp), name.slice(sp + 1)] : [name.slice(0, 9), name.slice(9)];
}

function edgePath(a, b) {
  const A = geo(a), B = geo(b);
  if (A.row === B.row) return { d: `M${A.x + A.w} ${A.y + A.h / 2}H${B.x - 2}`, lx: (A.x + A.w + B.x) / 2, ly: A.y + A.h / 2 - 6 };
  if (A.col === B.col) {
    const down = B.row > A.row;
    const y1 = down ? A.y + A.h : A.y, y2 = down ? B.y - 2 : B.y + B.h + 2;
    return { d: `M${A.x + A.w / 2} ${y1}V${y2}`, lx: A.x + A.w / 2 + 6, ly: (y1 + y2) / 2 };
  }
  const x1 = A.x + A.w, y1 = A.y + A.h / 2, x2 = B.x - 2, y2 = B.y + B.h / 2;
  if (x2 > x1 + 20) {
    const mx = (x1 + x2) / 2;
    return { d: `M${x1} ${y1}C${mx} ${y1} ${mx} ${y2} ${x2} ${y2}`, lx: mx + 4, ly: (y1 + y2) / 2 };
  }
  // 뒤로 가는 연결 (예: 분리 → 추출): 아래로 내려가 왼쪽으로
  const midY = (A.row < B.row ? A.y + A.h : A.y) + (A.row < B.row ? 14 : -14);
  const bx = B.x + B.w / 2, by = A.row < B.row ? B.y - 2 : B.y + B.h + 2;
  return { d: `M${A.x + A.w / 2} ${A.y + (A.row < B.row ? A.h : 0)}V${midY}H${bx}V${by}`, lx: (A.x + bx) / 2, ly: midY - 4 };
}

function svg(app) {
  const { stages, lanes } = app.meta.registry;
  const byId = Object.fromEntries(stages.map(s => [s.id, s]));
  const W = LABEL_W + COLS * COL_W + 10, H = TOP + lanes.length * ROW_H + 10;
  let out = `<svg class="arch" viewBox="0 0 ${W} ${H}" role="img" aria-label="Faultline 전체 시스템 구조도 — 스테이지 ${stages.length}개, 층 ${lanes.length}개">
    <defs><marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z"/></marker></defs>`;
  lanes.forEach((ln, i) => {
    const y = TOP + i * ROW_H + 3;
    const [t, s] = ln.name.split(" · ");
    out += `<rect class="lane-bg ${ln.id === "evaluator" ? "vault" : ""}" x="4" y="${y}" width="${W - 8}" height="${ROW_H - 6}" rx="12"/>
      <text class="lane-t" x="16" y="${y + ROW_H / 2 - 4}">${esc(t)}</text>${s ? `<text class="lane-s" x="16" y="${y + ROW_H / 2 + 12}">${esc(s)}</text>` : ""}`;
  });
  const by = TOP + ROW_H;
  out += `<line class="barrier" x1="4" y1="${by}" x2="${W - 4}" y2="${by}"/><text class="barrier-t" x="${W - 12}" y="${by - 6}" text-anchor="end">정보 차단선 — 아래 층은 hidden/ 을 읽을 수 없다 (코드로 강제)</text>`;
  stages.forEach(s => (s.after || []).forEach(a => {
    if (!byId[a]) return;
    const p = edgePath(byId[a], s), key = `${a}>${s.id}`;
    const cross = (byId[a].lane === "evaluator") !== (s.lane === "evaluator");
    out += `<path class="edge ${cross ? "cross" : ""}" d="${p.d}"/>`;
    if (EDGE_LABEL[key]) out += `<text class="elbl" x="${p.lx}" y="${p.ly}">${esc(EDGE_LABEL[key])}</text>`;
  }));
  stages.forEach(s => {
    const g = geo(s), lines = wrap(s.name), st = stageStatus(app, s.id);
    const sub = s.kind === "llm" ? `LLM · ${s.model}` : KIND[s.kind];
    out += `<g class="node ${st} ${app.sel.stage === s.id ? "sel" : ""}" data-id="${s.id}" tabindex="0" role="button" aria-label="${esc(s.num + " " + s.name)}">
      <rect x="${g.x}" y="${g.y}" width="${g.w}" height="${g.h}" rx="10"/>
      <text class="t" x="${g.x + 10}" y="${g.y + 19}">${esc(s.num)} ${esc(lines[0])}</text>
      ${lines[1] ? `<text class="t" x="${g.x + 10}" y="${g.y + 35}">${esc(lines[1])}</text>` : ""}
      <text class="s" x="${g.x + 10}" y="${g.y + g.h - 9}">${esc(sub)}${s.optional ? " · 선택" : ""}</text></g>`;
  });
  return out + "</svg>";
}

function detail(app) {
  const s = app.meta.registry.stages.find(x => x.id === app.sel.stage);
  if (!s) return `<p class="muted small">칸을 누르면 그 스테이지의 입력·출력·상태가 여기에 나온다.</p>`;
  const st = (app.state.stages || []).find(x => x.id === s.id) || {};
  const outs = (st.outputs || []).map(o => `<li><code>${esc(o.key)}</code> ${o.exists ? badge(o.count + "개", "ok") + ` <span class="tiny muted">${esc(o.updated || "")}</span>` : badge("없음")}</li>`).join("");
  return `<div class="row between"><h2 style="margin:0">${esc(s.num)} ${esc(s.name)}</h2>
      <div class="row">${badge(KIND[s.kind])}${s.model ? badge(s.model) : ""}${s.hidden ? badge("hidden 접근", "gt") : ""}${s.optional ? badge("선택") : ""}</div></div>
    <p style="margin-top:8px">${esc(s.desc)}</p>
    <dl class="kv"><dt>입력</dt><dd>${s.reads.map(k => `<code>${esc(k)}</code>`).join(" · ") || "—"}</dd>
      <dt>출력</dt><dd><ul style="margin:0;padding-left:18px">${outs || "<li>저장 없음 (계산 결과만)</li>"}</ul></dd>
      <dt>최근 작업</dt><dd>${st.last_job ? `${statusBadge(st.last_job.status)} <span class="small muted">${esc(st.last_job.executor)} · ${esc(st.last_job.model)} · ${esc(st.last_job.created)}</span>` : "—"}</dd>
      ${s.prompt ? `<dt>프롬프트</dt><dd><code>prompts/${esc(s.prompt)}</code></dd>` : ""}</dl>
    <div class="actions"><button class="btn primary" data-go="pipeline">파이프라인에서 열기</button></div>`;
}

export function render(app, el) {
  const { lanes, stages } = app.meta.registry;
  el.innerHTML = `<section class="card">
      <div class="row between"><h2 style="margin:0">전체 구조</h2><span class="small muted">초록 = 산출물 있음 · 주황 점선 = 실행 중 · 빨강 = 실패 · 점선 화살표 = 차단선을 넘는 흐름</span></div>
      <p class="small muted" style="margin-top:8px">이 그림은 백엔드의 스테이지 등록부에서 그려진다. 스테이지를 추가하면 그림도 따라 바뀐다.</p>
      <div class="scroll">${svg(app)}</div>
    </section>
    <section class="card" id="stageDetail">${detail(app)}</section>
    <section class="grid2">${lanes.map(l => `<div class="card flat"><h4 style="margin-top:0">${esc(l.name)}</h4><p class="small muted">${esc(l.desc)}</p>
      <div class="row">${stages.filter(s => s.lane === l.id).map(s => `<button class="btn sm" data-stage="${s.id}">${esc(s.num)} ${esc(s.name)}</button>`).join("")}</div></div>`).join("")}</section>
    <section class="card"><details><summary><b>스테이지 표</b> <span class="small muted">(구조도의 표 보기)</span></summary><div class="scroll" style="margin-top:8px"><table>
      <thead><tr><th>번호</th><th>스테이지</th><th>층</th><th>방식</th><th>입력</th><th>출력</th></tr></thead><tbody>
      ${stages.map(s => `<tr><td class="mono">${esc(s.num)}</td><td>${esc(s.name)}</td><td class="small">${esc(s.lane)}</td><td class="small">${esc(s.kind === "llm" ? "LLM · " + s.model : KIND[s.kind])}</td>
        <td class="small">${s.reads.map(esc).join(", ")}</td><td class="small">${s.writes.map(esc).join(", ")}</td></tr>`).join("")}</tbody></table></div></details></section>`;
  const pick = id => { app.sel.stage = id; render(app, el); document.getElementById("stageDetail").scrollIntoView({ block: "nearest" }); };
  el.querySelectorAll(".arch .node").forEach(n => {
    n.onclick = () => pick(n.dataset.id);
    n.onkeydown = e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pick(n.dataset.id); } };
  });
  el.querySelectorAll("[data-stage]").forEach(b => b.onclick = () => pick(b.dataset.stage));
  el.querySelectorAll("[data-go]").forEach(b => b.onclick = () => app.go(b.dataset.go, { focusStage: app.sel.stage }));
}
