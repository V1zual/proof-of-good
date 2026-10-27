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
const ph = (name) => `<i class="ph ph-${name}" aria-hidden="true"></i>`;
const ICON = { generator: "lightning", shelter: "fire", paws: "paw-print", try: "flask" };
const icon = (c) => ph(ICON[c.id] || "hand-heart");
// ledger lines start with an emoji for Telegram; on the site the row's own icon already says it
const plain = (s) => String(s ?? "").replace(/^\p{Extended_Pictographic}[️‍]*\s*/u, "");
const emptyHtml = (i, title, text) => `<div class="empty">${ph(i)}<div><b>${title}</b>${text}</div></div>`;

// the page shape while its data loads
{
  const el = $("#app");
  if (el && !el.innerHTML.trim()) el.innerHTML = `<div aria-busy="true" aria-label="Loading"><span class="skeleton sk-nav"></span><span class="skeleton sk-title"></span>
    <span class="skeleton sk-line"></span><div class="sk-cards"><span class="skeleton sk-card"></span><span class="skeleton sk-card"></span><span class="skeleton sk-card"></span></div></div>`;
}

function header(active) {
  const link = (href, key, text) => `<a href="${href}"${active === key ? ' aria-current="page"' : ""}>${text}</a>`;
  const links = link("/campaigns", "campaigns", "Campaigns") + link("/ledger", "ledger", "Ledger") + link("/volunteer", "volunteer", "Volunteer portal");
  return `<nav class="nav" aria-label="Main"><a class="brand" href="/"><span class="mark" aria-hidden="true">✓</span>Proof of Good</a>
    <div class="links">${links}</div><a class="btn btn-sm nav-cta" href="/c/try">Try it</a>
    <button class="menu-btn" type="button" aria-label="Open the menu" aria-expanded="false" aria-controls="panel"><i></i><i></i></button></nav>
    <div class="panel" id="panel" aria-hidden="true"><a href="/">Home</a>${links}<a href="/c/try">Try the full flow</a></div>`;
}

function setMenu(open) {
  document.body.classList.toggle("menu-open", open);
  const b = $(".menu-btn"), p = $("#panel");
  if (b) { b.setAttribute("aria-expanded", open); b.setAttribute("aria-label", open ? "Close the menu" : "Open the menu"); }
  if (p) p.setAttribute("aria-hidden", !open);
}
document.addEventListener("click", (e) => {
  if (e.target.closest(".menu-btn")) setMenu(!document.body.classList.contains("menu-open"));
  else if (e.target.closest(".panel a")) setMenu(false);
});
addEventListener("keydown", (e) => { if (e.key === "Escape") setMenu(false); });

function footer(cfg) {
  return `<footer class="foot"><span>Proof of Good · built for the PayPal AI Hackathon 2026${cfg && cfg.sandbox ? ' · <span class="badge sandbox">PayPal sandbox, test money</span>' : ""}</span>
    <nav aria-label="Footer"><a href="/campaigns">Campaigns</a><a href="/ledger">Ledger</a>${cfg && cfg.bot ? `<a href="https://t.me/${cfg.bot}">Telegram bot</a>` : ""}<a href="https://github.com/V1zual/proof-of-good" target="_blank" rel="noopener">Source</a><a href="/privacy">Privacy</a><a href="/terms">Terms</a></nav></footer>`;
}

function failPage(e) {
  $("#app").innerHTML = header("") + `<main id="main" class="page-head" role="alert">${emptyHtml("warning-circle", "This page did not load",
    `${esc(e && e.message ? e.message : e)}. Check your connection and <a href="">reload the page</a>.`)}</main>` + footer(CONFIG);
}

function moneyBar(t) {
  const goal = t.goal || 1, pct = (v) => Math.max(0, Math.min(100, (v / goal) * 100));
  const acc = pct(t.accounted), card = pct(t.released - t.accounted), held = pct(t.held);
  return `<div class="bar" role="img" aria-label="${money0(t.accounted)} spent and proven, ${money0(t.released - t.accounted)} on the card, ${money0(t.held)} held on PayPal, of a ${money0(t.goal)} goal"><i class="paid" style="width:${acc}%"></i><i class="oncard" style="width:${card}%"></i><i class="held" style="width:${held}%"></i></div>
    <div class="legend"><span><b>${money0(t.raised)}</b> of ${money0(t.goal)} raised</span>
    <span><i class="dot paid"></i><b>${money0(t.accounted)}</b> spent &amp; proven</span>
    <span><i class="dot oncard"></i><b>${money0(t.released - t.accounted)}</b> on the card</span>
    <span><i class="dot held"></i><b>${money0(t.held)}</b> held on PayPal</span>
    ${t.refunded ? `<span><i class="dot ref"></i><b>${money0(t.refunded)}</b> refunded</span>` : ""}</div>`;
}

const STATE = {
  waiting: ["wait", "waiting"], released: ["oncard", "on the card"], accounted: ["ok", "spent & proven"],
  refunded: ["bad", "refunded"], surplus: ["held", "held · over the goal"], held: ["held", "held"],
  matched: ["ok", "matches"], unclear: ["review", "needs a receipt"], flagged: ["bad", "flagged"], income: ["wait", "top up"],
};
const badge = (s) => { const [c, l] = STATE[s] || ["wait", s]; return `<span class="badge ${c}">${l}</span>`; };

function frozenBanner(c) {
  if (c.status !== "frozen") return "";
  return `<div class="note bad" role="status">${ph("snowflake")}<b>Spending frozen.</b> ${esc(c.frozen_reason || "")}<br>
    No more money goes to the card. The money still held on PayPal goes back to the donors.</div>`;
}

function checksHtml(checks) {
  return `<ul class="checks">${(checks || []).map((c) => `<li class="${c.ok === true ? "ok" : c.ok === false ? "bad" : "na"}"><b>${esc(c.name)}:</b> ${esc(c.detail)}</li>`).join("")}</ul>`;
}

function proofsHtml(proofs) {
  if (!proofs || !proofs.length) return "";
  const alt = (k) => (k === "receipt" ? "Receipt for the purchase" : "Photo of the purchase where it is used");
  return `<div class="proofs">${proofs.map((p) => `<a href="/uploads/${p.file}" target="_blank" rel="noopener"><img src="/uploads/${p.file}" alt="${alt(p.kind)}" loading="lazy"></a>`).join("")}</div>`;
}

const TX_ICON = { matched: "check-circle", unclear: "question", flagged: "prohibit", income: "arrow-down-left" };
function txHtml(t) {
  const amt = t.amount < 0 ? `−${uah(t.amount)}` : `+${uah(t.amount)}`;
  return `<li class="tx ${t.status}"><span class="ti ${t.status}">${ph(TX_ICON[t.status] || "circle")}</span>
    <div><b>${esc(t.description)}</b> <span class="muted">${esc(t.category || "")}${t.mcc ? ` · MCC ${t.mcc}` : ""}</span>
      <div>${esc(t.reason || "")}</div>
      <div class="xs muted mt-4">${when(t.at)}${t.receipt_id ? ` · fiscal receipt <span class="mono">${esc(t.receipt_id)}</span>` : ""}${t.simulated ? ' · <span class="badge wait">demo feed</span>' : ""}</div></div>
    <div class="tamt"><b>${amt}</b><div class="xs muted">${t.usd != null ? money(t.usd) : ""}</div></div></li>`;
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
    body += `<details class="report"><summary>${ph("caret-right")}AI audit: ${passed} of ${total} checks passed</summary>${checksHtml(v.checks)}</details>`;
  }
  if (t.release_batch) body += `<div class="xs muted mt-8">Released with PayPal payout <span class="mono">${esc(t.release_batch)}</span> · ${when(t.released_at)}</div>`;
  return `<li class="${t.status}"><div class="n">${t.status === "accounted" ? ph("check") : i + 1}</div>
    <div class="t-head"><div><b>${esc(t.title)}</b> ${badge(t.status)}</div><div class="t-amt">${money(t.amount)}</div></div>${body}</li>`;
}

const FEED_ICON = { donation: "hand-heart", release: "paper-plane-tilt", card: "credit-card", flag: "snowflake", proof: "paperclip",
  verdict: "robot", refund: "arrow-u-up-left", note: "note" };
function feedHtml(rows) {
  if (!rows.length) return emptyHtml("list-dashes", "Nothing here yet", "The first donation shows up in this list within seconds, with its PayPal id.");
  return `<ul class="feed">${rows.map((r) => `<li>${r.photo ? `<a href="/uploads/${r.photo}" target="_blank" rel="noopener"><img src="/uploads/${r.photo}" alt="Proof sent for this step" loading="lazy"></a>` : `<span class="fi ${r.kind}">${ph(FEED_ICON[r.kind] || "circle")}</span>`}
    <div>${esc(plain(r.text))}<time>${when(r.at)}${r.ref ? ` · <span class="mono">${esc(r.ref)}</span>` : ""}</time></div></li>`).join("")}</ul>`;
}
