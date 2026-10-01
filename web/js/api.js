// 백엔드 API 호출 — 프론트는 파일을 직접 만지지 않는다. 쓰기·검증·실행은 전부 서버가 한다.
async function call(method, url, body) {
  const opts = { method };
  if (body !== undefined) opts.body = typeof body === "string" ? body : JSON.stringify(body);
  const r = await fetch(url, opts);
  let j; try { j = await r.json(); } catch (e) { j = { error: "응답 파싱 실패 (" + r.status + ")" }; }
  if (!r.ok) { const err = new Error(j.error || ("HTTP " + r.status)); err.data = j; err.status = r.status; throw err; }
  return j;
}
const q = (root, extra = {}) => new URLSearchParams({ root, ...extra }).toString();

export const api = {
  meta: () => call("GET", "/api/meta"),
  executors: (refresh) => call("GET", "/api/executors" + (refresh ? "?refresh=1" : "")),
  docs: () => call("GET", "/api/docs"),
  doc: (name) => call("GET", "/api/docs/" + encodeURIComponent(name)),
  state: (root, evaluator) => call("GET", "/api/state?" + q(root, evaluator ? { evaluator: 1 } : {})),
  jobs: (root) => call("GET", "/api/jobs?" + q(root)),
  job: (root, id) => call("GET", `/api/jobs/${id}?` + q(root)),
  jobPrompt: (root, id, batch) => call("GET", `/api/jobs/${id}/prompt?` + q(root, { batch })),
  preview: (root, stage) => call("GET", "/api/preview?" + q(root, { stage })),
  createJob: (root, stage, executor, model) => call("POST", "/api/jobs?" + q(root, { stage, executor, model })),
  paste: (root, id, batch, text) => call("POST", `/api/jobs/${id}/paste?` + q(root, { batch }), text),
  finalize: (root, id, force) => call("POST", `/api/jobs/${id}/finalize?` + q(root, force ? { force: 1 } : {})),
  retry: (root, id) => call("POST", `/api/jobs/${id}/retry?` + q(root)),
  runDet: (root, stage) => call("POST", "/api/run?" + q(root, { stage })),
  score: (root) => call("POST", "/api/score?" + q(root)),
  review: (root, payload) => call("POST", "/api/review?" + q(root), payload),
  autorun: (root, from, to) => call("POST", "/api/autorun?" + q(root, { from: from || "", to: to || "" })),
  newExperiment: (body) => call("POST", "/api/experiments", body),
  setConfig: (root, body) => call("POST", "/api/config?" + q(root), body),
};
