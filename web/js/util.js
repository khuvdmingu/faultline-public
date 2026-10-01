// 공통 유틸
export const $ = (s, el = document) => el.querySelector(s);
export const $$ = (s, el = document) => [...el.querySelectorAll(s)];
export const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
export const by = arr => Object.fromEntries((arr || []).map(x => [x.id, x]));
export const fmt = v => v === null || v === undefined ? "—" : (typeof v === "number" && !Number.isInteger(v) ? v.toFixed(2) : String(v));
export const pct = v => v === null || v === undefined ? "—" : Math.round(v * 100) + "%";

export function badge(text, cls = "") { return `<span class="badge ${cls}">${esc(text)}</span>`; }

export function statusBadge(status) {
  const map = { done: ["완료", "ok"], waiting: ["붙여넣기 대기", "warn"], queued: ["대기열", "warn"], running: ["실행 중", "warn"],
                failed: ["실패", "bad"], needs_review: ["검증 오류 — 결정 필요", "bad"] };
  const [t, c] = map[status] || [status, ""];
  return badge(t, c);
}

export function highlight(text, excerpt) {
  const t = esc(text), e = esc(excerpt || "");
  return e && t.includes(e) ? t.replace(e, `<mark>${e}</mark>`) : t;
}

// 결정적 해시 → [0,1) — 산점도 지터용
export function hash01(s) {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); }
  return ((h >>> 0) % 10000) / 10000;
}

export function store(key, val) {
  try { if (val === undefined) return localStorage.getItem(key); localStorage.setItem(key, val); } catch (e) { return null; }
}

export async function copy(text) {
  try { await navigator.clipboard.writeText(text); return true; }
  catch (e) {
    const ta = document.createElement("textarea"); ta.value = text; document.body.appendChild(ta); ta.select();
    let ok = false; try { ok = document.execCommand("copy"); } catch (err) {} ta.remove(); return ok;
  }
}

// 에이전틱 시나리오 필드 (brief.technology 가 있을 때 40 이 채운다) — 정의 목록 행으로
export function agentRows(s) {
  if (!s || !(s.agent_actions || s.human_checkpoints || s.reversal)) return "";
  const li = xs => (xs || []).map(x => esc(x)).join("<br>") || "—";
  return `<dt>에이전트가 하는 일</dt><dd>${li(s.agent_actions)}</dd><dt>사람에게 묻는 순간</dt><dd>${li(s.human_checkpoints)}</dd>`
    + (s.reversal ? `<dt>되돌리기</dt><dd>${esc(s.reversal)}</dd>` : "");
}
