// 최소 Markdown 렌더러 — docs/ 의 문서를 보여주는 용도. 외부 라이브러리 없음.
// 지원: 제목, 문단, 목록(순서·비순서·체크박스), 표, 코드 블록, 인용, 굵게, 기울임, 인라인 코드, 링크, 구분선.
import { esc } from "./util.js";

function inline(s) {
  const codes = [];
  s = s.replace(/`([^`]+)`/g, (_, c) => { codes.push(c); return `\u0000${codes.length - 1}\u0000`; });
  s = esc(s)
    .replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>")
    .replace(/(^|[^*])\*([^*\s][^*]*)\*/g, "$1<i>$2</i>")
    .replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (_, t, u) => /^(https?:|#|\.{0,2}\/)/.test(u) || !/:/.test(u) ? `<a href="${u.replace(/"/g, "")}" ${/^https?:/.test(u) ? 'target="_blank" rel="noopener"' : ""}>${t}</a>` : t);
  return s.replace(/\u0000(\d+)\u0000/g, (_, i) => `<code>${esc(codes[+i])}</code>`);
}

export function renderMarkdown(src) {
  const lines = src.replace(/\r/g, "").split("\n");
  let out = [], i = 0;
  const para = [];
  const flush = () => { if (para.length) { out.push(`<p>${inline(para.join(" "))}</p>`); para.length = 0; } };
  while (i < lines.length) {
    const l = lines[i];
    if (/^```/.test(l)) {
      flush(); const buf = []; i++;
      while (i < lines.length && !/^```/.test(lines[i])) buf.push(lines[i++]);
      out.push(`<pre><code>${esc(buf.join("\n"))}</code></pre>`); i++; continue;
    }
    let m;
    if ((m = l.match(/^(#{1,4})\s+(.*)/))) { flush(); const n = m[1].length; const id = m[2].toLowerCase().replace(/[^\w가-힣]+/g, "-");
      out.push(`<h${n} id="${esc(id)}">${inline(m[2])}</h${n}>`); i++; continue; }
    if (/^\s*(-{3,}|\*{3,})\s*$/.test(l)) { flush(); out.push("<hr>"); i++; continue; }
    if (/^\|/.test(l) && i + 1 < lines.length && /^\|?\s*:?-{2,}/.test(lines[i + 1])) {
      flush();
      const row = x => x.replace(/^\||\|$/g, "").split("|").map(c => c.trim());
      const head = row(l); i += 2; const body = [];
      while (i < lines.length && /^\|/.test(lines[i])) body.push(row(lines[i++]));
      out.push(`<div class="scroll"><table><thead><tr>${head.map(h => `<th>${inline(h)}</th>`).join("")}</tr></thead><tbody>${body.map(r => `<tr>${r.map(c => `<td>${inline(c)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`);
      continue;
    }
    if (/^>\s?/.test(l)) { flush(); const buf = []; while (i < lines.length && /^>\s?/.test(lines[i])) buf.push(lines[i++].replace(/^>\s?/, ""));
      out.push(`<blockquote>${inline(buf.join(" "))}</blockquote>`); continue; }
    if ((m = l.match(/^(\s*)([-*]|\d+\.)\s+(.*)/))) {
      flush(); const ordered = /\d/.test(m[2]); const items = [];
      while (i < lines.length && (m = lines[i].match(/^(\s*)([-*]|\d+\.)\s+(.*)/))) {
        let t = m[3]; i++;
        while (i < lines.length && /^\s{2,}\S/.test(lines[i]) && !/^\s*([-*]|\d+\.)\s/.test(lines[i])) t += " " + lines[i++].trim();
        const cb = t.match(/^\[( |x)\]\s+(.*)/);
        items.push(cb ? `<li>${cb[1] === "x" ? "☑" : "☐"} ${inline(cb[2])}</li>` : `<li>${inline(t)}</li>`);
      }
      out.push(ordered ? `<ol>${items.join("")}</ol>` : `<ul>${items.join("")}</ul>`); continue;
    }
    if (!l.trim()) { flush(); i++; continue; }
    para.push(l.trim()); i++;
  }
  flush();
  return out.join("\n");
}
