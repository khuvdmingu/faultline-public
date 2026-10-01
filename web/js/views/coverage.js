// 커버리지 — 어떤 행동 공간이 비어 있는가 (설계 §12.4). 정답 없이 계산한다.
import { esc, badge, pct } from "../util.js";

const KIND_KO = { action: "일반 행동", avoidance: "회피", workaround: "우회", norm: "관습", edge: "극단", opinion: "의견", noise: "잡음" };
const PHASE_KO = { before: "감상 전", during: "감상 중", after: "감상 후", None: "불명" };

export function render(app, el) {
  const C = app.state.coverage;
  if (!C || !C.behaviors) { el.innerHTML = `<section class="card"><p class="empty">10 행동 추출 결과가 있어야 커버리지를 계산한다.</p></section>`; return; }
  const max = Math.max(1, ...C.kinds.flatMap(k => C.phases.map(p => C.kind_phase[k][p])));
  // 순차색 = 한 색상의 밝기만 (dataviz 규칙). 셀 숫자는 항상 텍스트 색.
  const cell = n => `<td class="heat" style="background:color-mix(in srgb, var(--seq) ${n ? 12 + Math.round(58 * n / max) : 0}%, transparent)">${n || "·"}</td>`;
  el.innerHTML = `<section class="card"><h2>공백</h2>
      ${C.gaps.length ? `<ul class="errs">${C.gaps.map(g => `<li>${esc(g)}</li>`).join("")}</ul><p class="tiny muted" style="margin-top:6px">공백이 곧 문제는 아니다 — 다음에 어떤 데이터를 더 모을지(또는 합성할지) 알려주는 신호다.</p>` : '<p class="small muted">눈에 띄는 공백 없음.</p>'}</section>
    <section class="grid2">
      <div class="card"><h2>행동 종류 × 감상 단계</h2><div class="scroll"><table>
        <thead><tr><th></th>${C.phases.map(p => `<th style="text-align:center">${esc(PHASE_KO[p] || p)}</th>`).join("")}</tr></thead>
        <tbody>${C.kinds.map(k => `<tr><th>${esc(KIND_KO[k] || k)}</th>${C.phases.map(p => cell(C.kind_phase[k][p])).join("")}</tr>`).join("")}</tbody></table></div>
        <p class="tiny muted">진할수록 많다. 단계가 「불명」이면 원문에 단계가 드러나지 않았다는 뜻이다 — 추출이 억지로 채우지 않은 것이 정상.</p></div>
      <div class="card"><h2>요약</h2><table>
        <tr><td>행동</td><td class="num">${C.behaviors}</td></tr>
        <tr><td>tension 에 연결</td><td class="num">${C.linked} (${pct(C.linked / C.behaviors)})</td></tr>
        <tr><td>연결 안 됨</td><td class="num">${C.unlinked}</td></tr>
        <tr><td>시나리오 · 평가됨</td><td class="num">${C.scenarios} · ${C.evaluated}</td></tr>
        <tr><td>미래 가정 horizon</td><td class="small">${Object.entries(C.horizons).map(([k, v]) => `${esc(k)} ${v}`).join(" · ") || "—"}</td></tr>
        <tr><td>family 크기</td><td class="small">${C.family_sizes.join(", ") || "—"}</td></tr>
        <tr><td>맥락 필드가 채워진 행동</td><td class="small">${["device", "social", "platform", "phase"].map(k => `${k} ${C.context_filled[k] || 0}`).join(" · ")}</td></tr></table></div>
    </section>
    <section class="card"><h2>tension 별</h2><div class="scroll"><table>
      <thead><tr><th>tension</th><th class="num">행동</th><th class="num">반례</th><th>종류 분포</th><th class="num">시나리오</th></tr></thead>
      <tbody>${C.per_tension.map(t => `<tr><td>${esc(t.id)} · ${esc(t.label)}</td><td class="num">${t.members}</td><td class="num">${t.counterexamples}</td>
        <td class="small">${Object.entries(t.kinds).map(([k, v]) => `${esc(KIND_KO[k] || k)} ${v}`).join(" · ")}</td><td class="num">${t.scenarios ? t.scenarios : badge("0", "warn")}</td></tr>`).join("")}</tbody></table></div></section>`;
}
