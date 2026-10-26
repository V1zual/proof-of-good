const $ = (s, el = document) => el.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const money = (v) => "$" + Number(v || 0).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const when = (t) => new Date(t * 1000).toLocaleString("en-GB", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
const api = async (path, opts = {}) => {
  const r = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || r.statusText);
  return data;
};
let CONFIG = null;
const config = async () => (CONFIG ||= await api("/api/config"));

function header(active) {
  return `<header class="top"><a class="brand" href="/"><span class="mark">✓</span>Proof of Good</a>
    <nav><a href="/" class="${active === "home" ? "active" : ""}">Campaigns</a>
    <a href="/ledger" class="${active === "ledger" ? "active" : ""}">Ledger</a>
    <a href="/volunteer" class="${active === "volunteer" ? "active" : ""}">Volunteer portal</a></nav></header>`;
}

function bar(t) {
  const goal = t.goal || 1;
  const paid = Math.min(100, t.paid / goal * 100), held = Math.min(100 - paid, t.held / goal * 100);
  return `<div class="bar"><i class="paid" style="width:${paid}%"></i><i class="held" style="width:${held}%"></i></div>
    <div class="nums"><span><b>${money(t.raised)}</b> raised of ${money(t.goal)}</span>
    <span><b>${money(t.paid)}</b> released · <b>${money(t.held)}</b> held</span></div>`;
}

const STATUS = { waiting: ["wait", "waiting for proof"], checking: ["review", "auditing…"], verified: ["ok", "verified, awaiting funds"],
  rejected: ["bad", "proof rejected"], review: ["review", "needs a human look"], paid: ["ok", "paid out"] };

function trancheHtml(t, i) {
  const [cls, label] = STATUS[t.status] || ["wait", t.status];
  const v = t.verdict;
  let extra = "";
  if (v) {
    extra += `<div class="sum">${esc(v.summary || "")}</div>`;
    if (v.checks) extra += `<ul class="checks">${v.checks.map((c) => `<li class="${c.ok === true ? "ok" : c.ok === false ? "bad" : "na"}">${esc(c.name)} — ${esc(c.detail)}</li>`).join("")}</ul>`;
    if (v.money && v.money.converted) extra += `<div class="small muted">Receipt ${v.money.receipt_total.toLocaleString()} ${esc(v.money.receipt_currency)} = ${money(v.money.converted)} at the ${esc(v.money.rate_source)} rate</div>`;
  }
  if (t.proofs && t.proofs.length) extra += `<div class="files">${t.proofs.map((p) => `<a href="/uploads/${p.file}" target="_blank"><img src="/uploads/${p.file}" alt="${p.kind}" title="${p.kind}"></a>`).join("")}</div>`;
  return `<div class="tranche ${t.status}"><div class="n">${t.status === "paid" ? "✓" : i + 1}</div>
    <div><b>${esc(t.title)}</b> <span class="badge ${cls}">${label}</span>${extra}</div>
    <div class="amt">${money(t.amount)}</div></div>`;
}

function feedHtml(rows) {
  if (!rows.length) return `<p class="muted">Nothing yet.</p>`;
  const icon = { donation: "💙", proof: "📎", verdict: "🤖", payout: "💸", refund: "↩️", note: "📝" };
  return `<ul class="feed">${rows.map((r) => `<li>${r.photo ? `<a href="/uploads/${r.photo}" target="_blank"><img src="/uploads/${r.photo}"></a>` : `<div class="ph">${icon[r.kind] || "•"}</div>`}
    <div>${esc(r.text)}<time>${when(r.at)}${r.ref ? ` · <span class="mono">${esc(r.ref)}</span>` : ""}</time></div></li>`).join("")}</ul>`;
}
