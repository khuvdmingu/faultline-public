// 문서 — docs/ 의 구조 문서·정책·계획을 서버에서 읽어 보여준다 (원본은 파일 하나).
import { api } from "../api.js";
import { esc } from "../util.js";
import { renderMarkdown } from "../md.js";

let cache = { list: null, docs: {} };

export async function render(app, el) {
  if (!cache.list) { el.innerHTML = `<section class="card"><p class="muted">불러오는 중…</p></section>`; cache.list = (await api.docs()).docs; }
  const cur = app.sel.doc || (cache.list.find(d => d.name === "ARCHITECTURE.md") || cache.list[0] || {}).name;
  if (cur && !cache.docs[cur]) cache.docs[cur] = (await api.doc(cur)).text;
  el.innerHTML = `<section class="split">
    <nav class="card list" aria-label="문서 목록"><h2>문서</h2>${cache.list.map(d => `<button data-d="${esc(d.name)}" aria-current="${d.name === cur}">${esc(d.title)}<small>docs/${esc(d.name)}</small></button>`).join("")}
      <p class="tiny muted" style="margin-top:8px">원본은 <code>docs/</code> 의 Markdown 파일이다. 여기서는 읽기만 한다.</p></nav>
    <article class="card doc">${cur ? renderMarkdown(cache.docs[cur]) : '<p class="empty">문서 없음</p>'}</article></section>`;
  el.querySelectorAll("[data-d]").forEach(b => b.onclick = () => { app.sel.doc = b.dataset.d; render(app, el); });
  el.querySelectorAll(".doc a[href]").forEach(a => {
    const href = a.getAttribute("href");
    if (/^https?:/.test(href)) return;
    const name = href.split("/").pop().split("#")[0];
    if (href.startsWith("#")) a.onclick = e => { e.preventDefault(); const t = el.querySelector(href); if (t) t.scrollIntoView(); };
    else if (/\.md$/.test(name) && cache.list.some(d => d.name === name)) a.onclick = e => { e.preventDefault(); app.sel.doc = name; render(app, el); };
    else if (/\.html$/.test(name)) { a.href = "/docs/" + name; a.target = "_blank"; a.rel = "noopener"; }
    else a.onclick = e => { e.preventDefault(); };   // 저장소 안 다른 파일 — 웹에서는 열지 않는다
  });
}
