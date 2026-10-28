// Drives a local demo server through a real sandbox run and captures the landing page screenshots (English and
// Ukrainian). Run after a sandbox buyer approved the donation order:
//   node docs/shots.js <base url> <approved order id> <out dir>
// Needs Node 22+ (fetch, WebSocket) and Chrome. States: card in use → AI check → frozen card → refund.
const { spawn } = require("child_process");
const fs = require("fs");
const path = require("path");

const [BASE = "http://localhost:8001", ORDER, OUT = "shots"] = process.argv.slice(2);
const CHROME = "C:/Program Files/Google/Chrome/Application/chrome.exe";
const PORT = 9333, W = 1280, H = 900;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const api = async (p, body) => {
  const r = await fetch(BASE + p, body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {});
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(`${p}: ${r.status} ${JSON.stringify(j)}`);
  return j;
};

// ---- a tiny Chrome DevTools client ----
let ws, seq = 0;
const pending = new Map();
function cdp(method, params = {}) {
  const id = ++seq;
  ws.send(JSON.stringify({ id, method, params }));
  return new Promise((res, rej) => pending.set(id, { res, rej }));
}
async function open() {
  const profile = path.resolve(OUT, "..", "..", "..", "_tmp", "cdp");
  spawn(CHROME, ["--headless=new", `--remote-debugging-port=${PORT}`, `--user-data-dir=${profile}`, "--hide-scrollbars", "--disable-gpu",
    `--window-size=${W},${H}`, "about:blank"], { stdio: "ignore", detached: true }).unref();
  let list;
  for (let i = 0; i < 40 && !list; i++) { await sleep(250); list = await fetch(`http://127.0.0.1:${PORT}/json/list`).then((r) => r.json()).catch(() => null); }
  const page = list.find((t) => t.type === "page");
  ws = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((r) => (ws.onopen = r));
  ws.onmessage = (m) => {
    const msg = JSON.parse(m.data);
    if (msg.id && pending.has(msg.id)) { const p = pending.get(msg.id); pending.delete(msg.id); msg.error ? p.rej(new Error(msg.error.message)) : p.res(msg.result); }
  };
  await cdp("Page.enable");
  await cdp("Emulation.setDeviceMetricsOverride", { width: W, height: H, deviceScaleFactor: 1, mobile: false });
}
const js = async (expr) => (await cdp("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true })).result.value;

// load a page and wait until its data (the element `sel`), fonts and translations are in place
async function load(url, sel = "main") {
  await cdp("Page.navigate", { url: BASE + url });
  for (let i = 0; i < 60; i++) {
    await sleep(500);
    const ready = await js(`document.readyState === "complete" && !!document.querySelector(${JSON.stringify(sel)}) && !document.querySelector("[aria-busy=true]")`);
    if (ready) break;
  }
  await js(`document.fonts.ready.then(() => true)`);
  for (let i = 0; i < 180; i++) {  // Ukrainian: live texts arrive from /api/translate
    if (!(await js(`document.querySelectorAll("[data-tr]").length`))) break;
    await sleep(500);
  }
  await sleep(1200);
}

// screenshot of the page from y to y + h (document coordinates), as webp through a png
async function shot(name, y = 0, h = H) {
  const { data } = await cdp("Page.captureScreenshot", { format: "png", captureBeyondViewport: true, clip: { x: 0, y, width: W, height: h, scale: 1 } });
  const file = path.join(OUT, name + ".png");
  fs.writeFileSync(file, Buffer.from(data, "base64"));
  console.log("saved", file);
}
// top of an element in document coordinates, minus some air
const top = (sel, air = 24) => js(`(() => { const el = document.querySelector(${JSON.stringify(sel)}); return el ? Math.max(0, Math.round(el.getBoundingClientRect().top + scrollY - ${air})) : 0; })()`);

async function both(fn) { for (const lang of ["en", "uk"]) await fn(lang); }

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  if (ORDER === "--audit") {  // again only the AI check pictures, from the campaign as it is now
    await open();
    await both(async (lang) => {
      await load(`/c/try?lang=${lang}`, "#c-bar");
      await js(`document.querySelectorAll("details.report").forEach((d) => (d.open = true)); true`);
      await sleep(600);
      await shot(`audit-${lang}`, await top("#c-tranches", 96), H);
    });
    await cdp("Browser.close").catch(() => {});
    process.exit(0);
  }
  if (ORDER === "--ledger") {  // again only the ledger: the table translates its lines after it draws, so load it twice
    await open();
    await both(async (lang) => {
      await load(`/ledger?lang=${lang}`, ".ag-root-wrapper");
      if (lang !== "en") { await sleep(20000); await load(`/ledger?lang=${lang}`, ".ag-root-wrapper"); }
      await shot(`ledger-${lang}`, 0, H);
    });
    await cdp("Browser.close").catch(() => {});
    process.exit(0);
  }
  // 1. the donation: capture the approved order, the first budget line goes to the card
  const cap = await api(`/api/orders/${ORDER}/capture`, {});
  const did = cap.donation.capture_id;
  console.log("donation", did, cap.donation.amount);
  await sleep(4000);
  // 2. the volunteer pays at a supermarket with the card
  console.log("store", (await api("/api/campaigns/try/card/simulate", { code: "TRY-IT", key: "store" })).status);
  await open();
  await both(async (lang) => {
    await load(`/c/try?lang=${lang}`, "#c-bar");
    await shot(`campaign-${lang}`, 0, H);
    await load(`/volunteer?code=TRY-IT&lang=${lang}`, "#cardbox");
    await shot(`volunteer-${lang}`, 0, H);
  });
  // 3. the AI check of the sample: a shop picture instead of a photo on site
  const c = await api("/api/volunteer/login", { code: "TRY-IT" });
  const tid = c.tranches.find((t) => t.status === "released").id;
  const fd = new FormData();
  fd.append("code", "TRY-IT");
  fd.append("photo", new Blob([fs.readFileSync(path.join(__dirname, "..", "static", "samples", "shop_photo.jpg"))], { type: "image/jpeg" }), "shop_photo.jpg");
  fd.append("receipt", new Blob([fs.readFileSync(path.join(__dirname, "..", "static", "samples", "shop_receipt.jpg"))], { type: "image/jpeg" }), "shop_receipt.jpg");
  const job = await fetch(`${BASE}/api/tranches/${tid}/evidence`, { method: "POST", body: fd }).then((r) => r.json());
  for (let i = 0; i < 120; i++) { await sleep(1000); const s = await api(`/api/jobs/${job.job}`); if (s.done) { console.log("audit", s.result && s.result.decision, s.error || ""); break; } }
  await both(async (lang) => {
    await load(`/c/try?lang=${lang}`, "#c-bar");
    await js(`document.querySelectorAll("details.report").forEach((d) => (d.open = true)); true`);
    await sleep(600);
    const y = await top("#c-tranches", 96);
    await shot(`audit-${lang}`, y, H);
  });
  // 4. cash at an ATM: the card freezes
  console.log("atm", (await api("/api/campaigns/try/card/simulate", { code: "TRY-IT", key: "atm" })).status);
  await sleep(1500);
  await both(async (lang) => {
    await load(`/c/try?lang=${lang}`, "#c-bar");
    await shot(`frozen-${lang}`, 0, H);
  });
  // 5. the money still held goes back to the donor
  const ref = await api("/api/campaigns/try/fail", { code: "TRY-IT", reason: "the card was used for a cash withdrawal" });
  console.log("refunds", JSON.stringify(ref).slice(0, 200));
  await sleep(2000);
  await both(async (lang) => {
    await load(`/ledger?lang=${lang}`, ".ag-root-wrapper");
    await shot(`ledger-${lang}`, 0, H);
    await load(`/d/${did}?lang=${lang}`, ".timeline");
    await shot(`donor-${lang}`, 0, H);
  });
  await cdp("Browser.close").catch(() => {});
  process.exit(0);
})().catch((e) => { console.error(e); process.exit(1); });
