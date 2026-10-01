// 채점·품질 — Phase 0 정답 대조(평가자 전용) + 합성 데이터 품질 검사 + 후반 지표.
import { api } from "../api.js";
import { esc, badge, fmt, pct } from "../util.js";

const MEANING = {
  excerpt_grounded: "근거 구절이 원문에 실제로 있다", hallucinated_context: "원문에 없는 기기·상황을 채웠다", negation_flip: "부정문을 뒤집었다",
  injection_leak: "원문 속 지시문을 따랐다", tension_recall: "심어둔 tension 을 되찾았다", distractor_intrusion: "무소속 원문이 tension 에 끌려 들어왔다",
  twin_merge: "같은 행동(쌍둥이)을 한데 묶었다", false_friend_split: "겉보기만 비슷한 것을 잘못 묶지 않았다", counterexample_kept: "반례가 반례로 남았다",
  trace_complete: "시나리오가 원문까지 이어진다",
};

function healthCard(H) {
  if (!H) return `<section class="card"><h2>후반 지표</h2><p class="empty small">시나리오가 있어야 계산한다.</p></section>`;
  return `<section class="card"><h2>후반 지표 <span class="tiny muted">정답 없이 계산 · 설계 §23.2</span></h2><div class="scroll"><table>
    <tr><td>평가 커버리지</td><td class="num">${pct(H.judge_coverage)}</td><td class="small muted">시나리오 중 judge 가 본 비율</td></tr>
    <tr><td>family 커버리지</td><td class="num">${pct(H.family_coverage)}</td><td class="small muted">family 에 배정된 비율 · family ${H.families}개</td></tr>
    <tr><td>뻔함 비율</td><td class="num">${pct(H.cliche_share)}</td><td class="small muted">뻔함 4~5점 또는 기준선과 겹친다고 판정된 비율</td></tr>
    <tr><td>발전 수율</td><td class="num">${pct(H.development_yield)}</td><td class="small muted">검토 ${H.reviewed}/${H.scenarios}</td></tr>
    <tr><td>발전한 독립 family 수율</td><td class="num">${pct(H.distinct_family_yield)}</td><td class="small muted">같은 family 의 반복을 한 번으로</td></tr></table></div></section>`;
}

function qaCard(Q) {
  if (!Q) return `<section class="card"><h2>합성 데이터 품질 검사</h2><p class="empty small">hidden/corpus_labeled.jsonl 이 있어야 검사한다.</p></section>`;
  const cls = s => s === "pass" ? "ok" : s === "fail" ? "bad" : "warn";
  return `<section class="card"><div class="row between"><h2 style="margin:0">합성 데이터 품질 검사 <span class="tiny muted">데이터 생성 정책 §7 의 자동 집행</span></h2>
      ${badge(Q.verdict, Q.fail ? "bad" : Q.warn ? "warn" : "ok")}</div>
    <p class="small muted" style="margin-top:6px">원문 ${Q.total}개 · FAIL 은 재생성 권장, 주의는 채점을 읽을 때 함께 본다. 이 검사가 FAIL 인 corpus 로 얻은 PASS 는 믿기 어렵다.</p>
    <div class="scroll"><table><thead><tr><th>검사</th><th>값</th><th>기준</th><th></th></tr></thead><tbody>
    ${Q.checks.map(c => `<tr><td>${esc(c.check)}</td><td class="small">${esc(Array.isArray(c.value) ? (c.value.length ? c.value.join(", ") : "없음") : c.value)}</td><td class="small muted">${esc(c.rule)}</td><td>${badge(c.status.toUpperCase(), cls(c.status))}</td></tr>`).join("")}
    </tbody></table></div></section>`;
}

export function render(app, el) {
  const st = app.state;
  if (!app.evaluator) {
    el.innerHTML = `<section class="card"><div class="note warn">Phase 0 채점과 데이터 품질 검사는 정답 라벨을 쓴다. 상단의 <b>평가자 모드</b>를 켜야 보인다 — 블라인드 검토 중에는 켜지 않는다.</div></section>${healthCard(st.health)}`;
    return;
  }
  const s = st.score;
  let scoreHtml;
  if (!s) scoreHtml = `<p class="empty">labels·raw·behaviors 가 모두 있어야 채점할 수 있다.</p>`;
  else {
    const pass = s.verdicts.filter(v => v.verdict === "PASS").length, fail = s.verdicts.filter(v => v.verdict === "FAIL").length;
    const d = s.detail;
    const det = [["hallucinated_context", "원문에 없는 맥락"], ["hallucinated_context_literal", "└ 그중 값이 원문에 글자로 있음 (생성 라벨 오류 의심)"], ["negation_flip", "부정 뒤집힘"], ["injection_leak", "지시문 누출"], ["distractor_intrusion", "무소속 침입"],
      ["twin_merge_failed", "쌍둥이 분리됨"], ["false_friend_fooled", "거짓 친구에 속음"], ["counterexample_lost", "반례 유실"], ["trace_broken", "추적 끊김"], ["kind_mismatch", "행동 종류 불일치 (참고)"]]
      .filter(([k]) => d[k] && d[k].length).map(([k, n]) => `<tr><td>${n}</td><td class="small">${d[k].map(x => esc(Array.isArray(x) ? x.join("↔") : x)).join(", ")}</td></tr>`).join("");
    scoreHtml = `<div class="row">${badge("PASS " + pass, "ok")}${badge("FAIL " + fail, fail ? "bad" : "")}${st.qa && st.qa.fail ? badge("데이터 품질 FAIL — 해석 주의", "warn") : ""}</div>
      <div class="scroll" style="margin-top:8px"><table><thead><tr><th>지표</th><th>의미</th><th class="num">값</th><th class="num">n</th><th>기준</th><th>판정</th></tr></thead><tbody>
      ${s.verdicts.map(v => `<tr><td class="mono small">${esc(v.metric)}</td><td class="small muted">${MEANING[v.metric] || ""}</td><td class="num">${fmt(v.value)}</td><td class="num small muted">${v.n ?? ""}</td><td class="small muted">${esc(v.rule)}</td>
        <td>${badge(v.verdict, v.verdict === "PASS" ? "ok" : v.verdict === "FAIL" ? "bad" : "")}${v.small ? ` <span class="tiny muted" title="분모가 5 미만 — 한 건이 판정을 뒤집는다">표본 작음</span>` : ""}</td></tr>`).join("")}</tbody></table></div>
      ${s.verdicts.some(v => v.small) ? `<p class="tiny muted" style="margin-top:6px">「표본 작음」 = 분모 5 미만. quick 크기는 함정·반례가 2~4개라 한 건이 판정을 뒤집는다 — 연결 로직 판단은 standard 또는 여러 실험 합산으로.</p>` : ""}
      <h3>심어둔 tension 재발견</h3><div class="scroll"><table><thead><tr><th>정답</th><th>매칭된 tension</th><th class="num">순도</th><th class="num">커버</th><th></th></tr></thead><tbody>
      ${d.tension_recall.map(r => { const g = (st.ground_truth.tensions || []).find(x => x.id === r.hidden);
        return `<tr><td>${esc(r.hidden)}${g ? `<div class="tiny muted">${esc(g.pole_a)} ↔ ${esc(g.pole_b)}${g.familiarity ? " · " + esc(g.familiarity) : ""}</div>` : ""}</td><td>${esc(r.matched || "—")}</td>
          <td class="num">${r.purity ?? "—"}</td><td class="num">${r.coverage ?? "—"}</td><td>${badge(r.recovered ? "재발견" : "놓침", r.recovered ? "ok" : "bad")}</td></tr>`; }).join("")}</tbody></table></div>
      ${det ? `<h3>틀린 곳</h3><div class="scroll"><table><tbody>${det}</tbody></table></div>` : ""}
      <p class="tiny muted" style="margin-top:8px">계산 ${esc(s.at)} · 기준값은 docs/PHASE0_PLAN.md 와 engine/scoring.py 에서 함께 바꾼다.</p>`;
  }
  el.innerHTML = `<section class="card"><div class="row between"><h2 style="margin:0">Phase 0 채점 — 정답 라벨 대조</h2><button class="btn primary sm" id="runScore">채점 저장</button></div>
      <div style="margin-top:10px">${scoreHtml}</div><div class="msg" id="smsg"></div></section>
    ${qaCard(st.qa)}${healthCard(st.health)}`;
  el.querySelector("#runScore").onclick = async () => {
    try { const r = await api.score(app.root); el.querySelector("#smsg").className = "msg ok"; el.querySelector("#smsg").textContent = "저장 → runs/score/phase0.json (" + r.at + ")"; }
    catch (e) { el.querySelector("#smsg").className = "msg bad"; el.querySelector("#smsg").textContent = e.message; }
  };
}
