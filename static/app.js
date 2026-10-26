const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const money = (v) => "$" + Number(v || 0).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const money0 = (v) => "$" + Math.round(Number(v || 0)).toLocaleString("en-US");
const when = (t) => new Date(t * 1000).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
const api = async (path, opts = {}) => {
  const r = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || r.statusText);
  return data;
};
let CONFIG = null;
const config = async () => (CONFIG ||= await api("/api/config"));
const ICON = { generator: "⚡", shelter: "🔥", paws: "🐾" };
const icon = (c) => ICON[c.id] || "💙";

function header(active) {
  const link = (href, key, text) => `<a href="${href}" class="${active === key ? "active" : ""}">${text}</a>`;
  return `<header class="top"><a class="brand" href="/"><span class="mark">✓</span>Proof of Good</a>
    <nav>${link("/", "home", "Campaigns")}${link("/ledger", "ledger", "Ledger")}${link("/volunteer", "volunteer", "Volunteer portal")}</nav></header>`;
}

function footer(cfg) {
  return `<footer class="foot"><span>Proof of Good · built for the PayPal AI Hackathon 2026 · PayPal Orders, Payouts &amp; Refunds + Gemini</span>
    <span>${cfg && cfg.sandbox ? '<span class="badge sandbox">PayPal sandbox · test money</span>' : ""}
    ${cfg && cfg.bot ? ` · <a href="https://t.me/${cfg.bot}">Telegram bot</a>` : ""} · <a href="https://github.com/V1zual/proof-of-good">Source</a></span></footer>`;
}

function moneyBar(t) {
  const goal = t.goal || 1;
  const paid = Math.min(100, (t.paid / goal) * 100), held = Math.min(100 - paid, (t.held / goal) * 100);
  return `<div class="bar"><i class="paid" style="width:${paid}%"></i><i class="held" style="width:${held}%"></i></div>
    <div class="legend"><span><b>${money0(t.raised)}</b> of ${money0(t.goal)} raised</span>
    <span><i class="dot paid"></i><b>${money0(t.paid)}</b> released</span>
    <span><i class="dot held"></i><b>${money0(t.held)}</b> held</span>
    ${t.refunded ? `<span><i class="dot ref"></i><b>${money0(t.refunded)}</b> refunded</span>` : ""}</div>`;
}

const STATE = {
  waiting: ["wait", "waiting for proof"], checking: ["review", "auditing…"], verified: ["ok", "verified · awaiting funds"],
  rejected: ["bad", "proof rejected"], review: ["review", "needs a human look"], paid: ["ok", "released"],
  held: ["held", "held"], refunded: ["bad", "refunded"], surplus: ["held", "held · over the goal"],
};
const badge = (s) => { const [c, l] = STATE[s] || ["wait", s]; return `<span class="badge ${c}">${l}</span>`; };

function checksHtml(checks) {
  return `<ul class="checks">${(checks || []).map((c) => `<li class="${c.ok === true ? "ok" : c.ok === false ? "bad" : "na"}"><b>${esc(c.name)}</b> — ${esc(c.detail)}</li>`).join("")}</ul>`;
}

function proofsHtml(proofs) {
  if (!proofs || !proofs.length) return "";
  return `<div class="proofs">${proofs.map((p) => `<a href="/uploads/${p.file}" target="_blank" title="${p.kind}"><img src="/uploads/${p.file}" alt="${p.kind}" loading="lazy"></a>`).join("")}</div>`;
}

function trancheHtml(t, i) {
  const v = t.verdict;
  let body = "";
  if (v && v.summary && (t.status === "paid" || t.status === "verified")) body += `<div class="t-sum">${esc(v.summary)}</div>`;
  else if (v && v.reasons && v.reasons.length) body += `<div class="t-sum">${esc(v.reasons[0])}</div>`;
  body += proofsHtml(t.proofs);
  if (v && v.checks) {
    const passed = v.checks.filter((c) => c.ok === true).length, total = v.checks.filter((c) => c.ok !== null).length;
    body += `<details class="report"><summary>AI audit: ${passed}/${total} checks passed${v.money && v.money.converted ? ` · receipt ${money(v.money.converted)}` : ""}</summary>${checksHtml(v.checks)}</details>`;
  }
  if (t.paid_batch) body += `<div class="small muted" style="margin-top:6px">PayPal payout <span class="mono">${esc(t.paid_batch)}</span> · ${when(t.paid_at)}</div>`;
  return `<li class="${t.status}"><div class="n">${t.status === "paid" ? "✓" : i + 1}</div>
    <div class="t-head"><div><b>${esc(t.title)}</b> ${badge(t.status)}</div><div class="t-amt">${money(t.amount)}</div></div>${body}</li>`;
}

function feedHtml(rows) {
  if (!rows.length) return `<p class="muted">Nothing yet.</p>`;
  const ico = { donation: "💙", proof: "📎", verdict: "🤖", payout: "💸", refund: "↩️", note: "📝" };
  return `<ul class="feed">${rows.map((r) => `<li>${r.photo ? `<a href="/uploads/${r.photo}" target="_blank"><img src="/uploads/${r.photo}" loading="lazy"></a>` : `<div class="ph">${ico[r.kind] || "•"}</div>`}
    <div>${esc(r.text)}<time>${when(r.at)}${r.ref ? ` · <span class="mono">${esc(r.ref)}</span>` : ""}</time></div></li>`).join("")}</ul>`;
}
