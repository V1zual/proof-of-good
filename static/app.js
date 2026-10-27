const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const money = (v) => "$" + Number(v || 0).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const money0 = (v) => "$" + Math.round(Number(v || 0)).toLocaleString("en-US");
const uah = (v) => "₴" + Math.abs(Number(v || 0)).toLocaleString("en-US", { maximumFractionDigits: 0 });
const when = (t) => new Date(t * 1000).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
const api = async (path, opts = {}) => {
  const r = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || r.statusText);
  return data;
};
let CONFIG = null;
const config = async () => (CONFIG ||= await api("/api/config"));
const ICON = { generator: "⚡", shelter: "🔥", paws: "🐾", try: "🧪" };
const icon = (c) => ICON[c.id] || "💙";

function header(active) {
  const link = (href, key, text) => `<a href="${href}" class="${active === key ? "active" : ""}">${text}</a>`;
  return `<header class="top"><a class="brand" href="/"><span class="mark">✓</span>Proof of Good</a>
    <nav>${link("/", "home", "Campaigns")}${link("/ledger", "ledger", "Ledger")}${link("/volunteer", "volunteer", "Volunteer portal")}</nav></header>`;
}

function footer(cfg) {
  return `<footer class="foot"><span>Proof of Good · PayPal AI Hackathon 2026 · PayPal Orders, Payouts &amp; Refunds + Gemini + a bank feed</span>
    <span>${cfg && cfg.sandbox ? '<span class="badge sandbox">PayPal sandbox · test money</span>' : ""}
    ${cfg && cfg.bot ? ` · <a href="https://t.me/${cfg.bot}">Telegram bot</a>` : ""} · <a href="https://github.com/V1zual/proof-of-good">Source</a></span></footer>`;
}

function moneyBar(t) {
  const goal = t.goal || 1, pct = (v) => Math.max(0, Math.min(100, (v / goal) * 100));
  const acc = pct(t.accounted), card = pct(t.released - t.accounted), held = pct(t.held);
  return `<div class="bar"><i class="paid" style="width:${acc}%"></i><i class="card" style="width:${card}%"></i><i class="held" style="width:${held}%"></i></div>
    <div class="legend"><span><b>${money0(t.raised)}</b> of ${money0(t.goal)} raised</span>
    <span><i class="dot paid"></i><b>${money0(t.accounted)}</b> spent &amp; proven</span>
    <span><i class="dot card"></i><b>${money0(t.released - t.accounted)}</b> on the card</span>
    <span><i class="dot held"></i><b>${money0(t.held)}</b> held on PayPal</span>
    ${t.refunded ? `<span><i class="dot ref"></i><b>${money0(t.refunded)}</b> refunded</span>` : ""}</div>`;
}

const STATE = {
  waiting: ["wait", "waiting"], released: ["card", "on the card"], accounted: ["ok", "spent & proven"],
  refunded: ["bad", "refunded"], surplus: ["held", "held · over the goal"], held: ["held", "held"],
  matched: ["ok", "matches"], unclear: ["review", "needs a receipt"], flagged: ["bad", "flagged"], income: ["wait", "top-up"],
};
const badge = (s) => { const [c, l] = STATE[s] || ["wait", s]; return `<span class="badge ${c}">${l}</span>`; };

function frozenBanner(c) {
  if (c.status !== "frozen") return "";
  return `<div class="note bad" style="margin-bottom:18px"><b>⛔ Spending frozen.</b> ${esc(c.frozen_reason || "")}<br>
    No more money goes to the card. The money still held on PayPal goes back to the donors.</div>`;
}

function checksHtml(checks) {
  return `<ul class="checks">${(checks || []).map((c) => `<li class="${c.ok === true ? "ok" : c.ok === false ? "bad" : "na"}"><b>${esc(c.name)}</b> — ${esc(c.detail)}</li>`).join("")}</ul>`;
}

function proofsHtml(proofs) {
  if (!proofs || !proofs.length) return "";
  return `<div class="proofs">${proofs.map((p) => `<a href="/uploads/${p.file}" target="_blank" title="${p.kind}"><img src="/uploads/${p.file}" alt="${p.kind}" loading="lazy"></a>`).join("")}</div>`;
}

function txHtml(t, withTranche) {
  const icon = { matched: "✅", unclear: "❔", flagged: "⛔", income: "⬇️" }[t.status] || "•";
  const amt = t.amount < 0 ? `−${uah(t.amount)}` : `+${uah(t.amount)}`;
  return `<li class="tx ${t.status}"><span class="ti">${icon}</span>
    <div><b>${esc(t.description)}</b> <span class="muted small">${esc(t.category || "")}${t.mcc ? ` · MCC ${t.mcc}` : ""}</span>
      <div class="small">${esc(t.reason || "")}</div>
      <div class="small muted">${when(t.at)}${t.receipt_id ? ` · fiscal receipt <span class="mono">${esc(t.receipt_id)}</span>` : ""}${t.simulated ? ' · <span class="badge wait">demo feed</span>' : ""}</div></div>
    <div class="tamt"><b>${amt}</b><div class="small muted">${t.usd != null ? money(t.usd) : ""}</div></div></li>`;
}

function trancheHtml(t, i) {
  const v = t.verdict;
  let body = "";
  if (t.status === "released") {
    const pct = Math.min(100, (t.spent / t.amount) * 100);
    body += `<div class="spend"><div class="bar thin"><i class="paid" style="width:${pct}%"></i></div>
      <div class="small muted">${money(t.spent)} of ${money(t.amount)} spent in checked card payments</div></div>`;
  }
  if (t.payments && t.payments.length) body += `<ul class="txs">${t.payments.map((x) => txHtml(x)).join("")}</ul>`;
  if (v && v.summary && t.status === "accounted") body += `<div class="t-sum">${esc(v.summary)}</div>`;
  else if (v && v.reasons && v.reasons.length) body += `<div class="t-sum">${esc(v.message_to_volunteer || v.reasons[0])}</div>`;
  body += proofsHtml(t.proofs);
  if (v && v.checks) {
    const passed = v.checks.filter((c) => c.ok === true).length, total = v.checks.filter((c) => c.ok !== null).length;
    body += `<details class="report"><summary>AI audit: ${passed}/${total} checks passed</summary>${checksHtml(v.checks)}</details>`;
  }
  if (t.release_batch) body += `<div class="small muted" style="margin-top:6px">Released with PayPal payout <span class="mono">${esc(t.release_batch)}</span> · ${when(t.released_at)}</div>`;
  return `<li class="${t.status}"><div class="n">${t.status === "accounted" ? "✓" : i + 1}</div>
    <div class="t-head"><div><b>${esc(t.title)}</b> ${badge(t.status)}</div><div class="t-amt">${money(t.amount)}</div></div>${body}</li>`;
}

function feedHtml(rows) {
  if (!rows.length) return `<p class="muted">Nothing yet.</p>`;
  const ico = { donation: "💙", release: "💸", card: "💳", flag: "⛔", proof: "📎", verdict: "🤖", refund: "↩️", note: "📝" };
  return `<ul class="feed">${rows.map((r) => `<li>${r.photo ? `<a href="/uploads/${r.photo}" target="_blank"><img src="/uploads/${r.photo}" loading="lazy"></a>` : `<div class="ph">${ico[r.kind] || "•"}</div>`}
    <div>${esc(r.text)}<time>${when(r.at)}${r.ref ? ` · <span class="mono">${esc(r.ref)}</span>` : ""}</time></div></li>`).join("")}</ul>`;
}
