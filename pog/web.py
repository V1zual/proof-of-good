"""The website: campaign pages with PayPal donate buttons, the volunteer portal with the transparent card, the bank
webhook, the public ledger, JSON API."""
import asyncio
import json
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import audit, cards, config, seed, service, store

log = logging.getLogger("pog.web")
STATIC = Path(__file__).resolve().parent.parent / "static"
ADMIN_KEY = os.environ.get("ADMIN_KEY", "")


@asynccontextmanager
async def lifespan(app: FastAPI):
    seed.seed()
    config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    tasks = [asyncio.create_task(_housekeeping()), asyncio.create_task(_warm_up())]
    if os.environ.get("RUN_BOT", "1") == "1":
        from . import bot
        tasks.append(asyncio.create_task(bot.run_in_background()))
    yield
    for t in tasks:
        t.cancel()


async def _warm_up():
    """The first audit after a deploy took ~70 s (cold imports and connections); pay that cost at start-up instead."""
    try:
        audit._c2pa(b"")
        await audit.uah_rate("USD")
        await audit._generate([{"text": "Reply with {\"ok\": true}"}],
                              {"type": "OBJECT", "properties": {"ok": {"type": "BOOLEAN"}}})
        log.info("warm-up done")
    except Exception:
        log.exception("warm-up")


async def _housekeeping():
    while True:
        try:
            await service.refresh_payouts()
        except Exception:
            log.exception("housekeeping")
        await asyncio.sleep(120)


app = FastAPI(title="Proof of Good", lifespan=lifespan)


@app.middleware("http")
async def revalidate(request: Request, call_next):
    """Pages and static files change with every deploy: browsers must ask (a cheap 304) instead of reusing an old copy.
    Uploaded proofs never change, so they keep the browser's default caching."""
    response = await call_next(request)
    if not request.url.path.startswith("/uploads/"):
        response.headers.setdefault("Cache-Control", "no-cache")
    return response


def _tx_view(t: dict) -> dict:
    return {k: t[k] for k in ("id", "tranche_id", "at", "description", "mcc", "amount", "currency", "usd",
                              "receipt_id", "status", "reason", "simulated")} | {"category": cards.MCC.get(t["mcc"], "")}


def _tranche_view(t: dict) -> dict:
    v = json.loads(t["verdict"]) if t.get("verdict") else None
    out = {k: t[k] for k in ("id", "position", "title", "amount", "status", "release_batch", "released_at",
                             "photo_ok", "accounted_at")}
    out["spent"] = store.spent(t["id"])
    out["payments"] = [_tx_view(x) for x in store.card_txs(t["campaign_id"], t["id"])]
    if v:
        out["verdict"] = {k: v.get(k) for k in ("decision", "accounted", "summary", "reasons", "checks", "spent",
                                                 "message_to_volunteer", "files", "via", "at")}
    out["proofs"] = [{"kind": p["kind"], "file": p["file"], "meta": json.loads(p["meta"] or "{}")}
                     for p in store.proofs(t["id"])]
    return out


def _campaign_view(c: dict, full: bool = False) -> dict:
    out = {k: c[k] for k in ("id", "title", "story", "place", "country", "volunteer_name", "currency", "status",
                             "frozen_reason", "card_mode", "card_label", "try_it", "created")}
    out["totals"] = store.totals(c["id"])
    out["tranches"] = [_tranche_view(t) for t in store.tranches(c["id"])]
    if full:
        out["ledger"] = store.ledger(c["id"])
        out["card_feed"] = [_tx_view(t) for t in store.card_txs(c["id"])]
    return out


def _volunteer(code: str) -> dict:
    c = store.campaign_by_code(code or "")
    if not c:
        raise HTTPException(403, "Wrong volunteer code")
    return c


# ---------- pages ----------

@app.api_route("/", methods=["GET", "HEAD"])
async def page_landing():
    return FileResponse(STATIC / "landing.html")


@app.api_route("/healthz", methods=["GET", "HEAD"])
async def healthz():
    return {"ok": True}


@app.get("/campaigns")
async def page_campaigns():
    return FileResponse(STATIC / "campaigns.html")


@app.get("/privacy")
async def page_privacy():
    return FileResponse(STATIC / "privacy.html")


@app.get("/terms")
async def page_terms():
    return FileResponse(STATIC / "terms.html")


@app.exception_handler(StarletteHTTPException)
async def not_found(request: Request, ex: StarletteHTTPException):
    """API callers get JSON as before; people who follow a dead link get the branded 404 page."""
    path = request.url.path
    if ex.status_code == 404 and not path.startswith(("/api/", "/hooks/")):
        return FileResponse(STATIC / "404.html", status_code=404)
    return JSONResponse({"detail": ex.detail}, status_code=ex.status_code, headers=getattr(ex, "headers", None))


@app.get("/c/{cid}")
async def page_campaign(cid: str):
    if not store.campaign(cid):
        raise HTTPException(404)
    return FileResponse(STATIC / "campaign.html")


@app.get("/volunteer")
async def page_volunteer():
    return FileResponse(STATIC / "volunteer.html")


@app.get("/ledger")
async def page_ledger():
    return FileResponse(STATIC / "ledger.html")


@app.get("/d/{did}")
async def page_donation(did: str):
    return FileResponse(STATIC / "donation.html")


# ---------- campaigns and donations ----------

@app.get("/api/config")
async def api_config():
    return {"paypal_client_id": config.secret("PAYPAL_CLIENT_ID"), "currency": "USD",
            "sandbox": "sandbox" in config.PAYPAL_API, "public_url": config.PUBLIC_URL,
            "sandbox_buyer": os.environ.get("SANDBOX_BUYER", ""), "bot": os.environ.get("BOT_USERNAME", ""),
            "monobank": config.ALLOW_MONOBANK}


@app.get("/api/campaigns")
async def api_campaigns():
    return [_campaign_view(c) for c in store.campaigns()]


@app.get("/api/campaigns/{cid}")
async def api_campaign(cid: str):
    c = store.campaign(cid)
    if not c:
        raise HTTPException(404)
    return _campaign_view(c, full=True)


@app.post("/api/campaigns/{cid}/orders")
async def api_order(cid: str, body: dict):
    try:
        return {"id": await service.start_donation(cid, float(body.get("amount", 0)))}
    except ValueError as ex:
        raise HTTPException(400, str(ex))


@app.post("/api/orders/{order_id}/capture")
async def api_capture(order_id: str):
    try:
        return await service.finish_donation(order_id)
    except Exception as ex:
        log.exception("capture")
        raise HTTPException(400, str(ex)[:300])


@app.get("/api/donations/{did}")
async def api_donation(did: str):
    d = store.donation(did)
    if not d:
        raise HTTPException(404)
    c = store.campaign(d["campaign_id"])
    parts = service.allocation(c["id"]).get(did, [])
    tranches = {t["id"]: _tranche_view(t) for t in store.tranches(c["id"])}
    for p in parts:
        if p.get("tranche"):
            p["detail"] = tranches[p["tranche"]]
    return {"donation": {k: d[k] for k in ("id", "amount", "currency", "status", "created", "donor_name")},
            "campaign": {k: c[k] for k in ("id", "title", "place", "volunteer_name", "status", "frozen_reason")},
            "totals": store.totals(c["id"]), "parts": parts}


@app.get("/api/ledger")
async def api_ledger():
    titles = {c["id"]: c["title"] for c in store.campaigns()}
    rows = store.ledger()
    for r in rows:
        r["campaign"] = titles.get(r["campaign_id"], r["campaign_id"])
    return rows


@app.get("/api/uah")
async def api_rate():
    return {"USD": await audit.uah_rate("USD"), "source": "National Bank of Ukraine"}


# ---------- live texts in Ukrainian and Russian ----------

TRANSLATED: dict[tuple[str, str], str] = {}  # (lang, English text) -> translation, shared by every visitor
_tr_lock = asyncio.Lock()
_tr_calls: list[float] = []
LANG_NAMES = {"uk": "Ukrainian", "ru": "Russian"}
TR_SCHEMA = {"type": "OBJECT", "properties": {"items": {"type": "ARRAY", "items": {"type": "STRING"}}},
             "required": ["items"]}


@app.post("/api/translate")
async def api_translate(body: dict):
    """Server texts the page shows (ledger lines, AI verdicts, bank categories) for the Ukrainian and Russian site.
    The page asks only for strings it has not seen; answers are cached for every visitor, and Gemini is called at
    most 20 times a minute so the auditor keeps its quota. Strings that could not be translated are left out."""
    lang = body.get("lang")
    if lang not in LANG_NAMES:
        raise HTTPException(400, "lang must be uk or ru")
    texts = list(dict.fromkeys(s for s in (str(x)[:600] for x in (body.get("texts") or [])[:60]) if s.strip()))
    async with _tr_lock:
        missing = [s for s in texts if (lang, s) not in TRANSLATED]
        now = time.time()
        _tr_calls[:] = [c for c in _tr_calls if now - c < 60]
        if missing and len(_tr_calls) < 20:
            _tr_calls.append(now)
            prompt = (f"Translate each English string into {LANG_NAMES[lang]} for a donation transparency website: "
                      "volunteers spend donations from a transparent bank card and an AI auditor checks every payment "
                      "and photo. Use the polite form of address. Keep unchanged: numbers, amounts with $ or ₴, ids, "
                      "codes, emoji, «» quotes, shop names and people's names. Answer {\"items\": [...]} with exactly "
                      "one translation per input string, in the same order.\n\n" + json.dumps(missing, ensure_ascii=False))
            try:
                out = (await audit._generate([{"text": prompt}], TR_SCHEMA)).get("items") or []
                if len(out) == len(missing):
                    if len(TRANSLATED) > 20000:
                        TRANSLATED.clear()
                    TRANSLATED.update({(lang, src): str(dst) for src, dst in zip(missing, out)})
                else:
                    log.warning("translate: %d strings in, %d out", len(missing), len(out))
            except Exception:
                log.exception("translate")
    return {s: TRANSLATED[(lang, s)] for s in texts if (lang, s) in TRANSLATED}


# ---------- volunteer: the card ----------

@app.post("/api/volunteer/login")
async def api_volunteer_login(body: dict):
    c = store.campaign_by_code(body.get("code", ""))
    if not c:
        raise HTTPException(404, "No campaign with this code")
    out = _campaign_view(c, full=True)
    tr = store.current_tranche(c["id"])
    out["presets"] = cards.demo_presets(tr, await audit.uah_rate("USD")) if c["card_mode"] == "demo" else []
    return out


@app.post("/api/campaigns/{cid}/card/simulate")
async def api_simulate(cid: str, body: dict):
    """Demo bank feed: makes the volunteer's simulated card pay, exactly as the Monobank webhook would report it."""
    c = _volunteer(body.get("code", ""))
    if c["id"] != cid or c["card_mode"] != "demo":
        raise HTTPException(400, "This campaign's card is not the demo card")
    if not store.current_tranche(cid) and body.get("key") != "income":
        raise HTTPException(400, "No tranche is on the card yet — it is released when enough money is donated")
    presets = {p["key"]: p for p in cards.demo_presets(store.current_tranche(cid), await audit.uah_rate("USD"))}
    if body.get("key") in presets:
        preset = presets[body["key"]]
    else:
        try:
            preset = {"key": "custom", "description": str(body["description"])[:80], "mcc": int(body["mcc"]),
                      "amount": -abs(float(body["amount"]))}
        except (KeyError, ValueError):
            raise HTTPException(400, "Pick a payment or give description, mcc and amount")
    tx = await service.card_payment(cid, cards.demo_tx(preset))
    return _tx_view(store.card_txs(cid)[0]) if tx else {}


@app.post("/api/volunteer/card")
async def api_link_card(body: dict):
    """Real mode: links a Monobank card with a read-only personal token and asks the bank for a webhook."""
    if not config.ALLOW_MONOBANK:
        raise HTTPException(403, "Real bank cards are switched off on this demo server")
    c = _volunteer(body.get("code", ""))
    token = (body.get("token") or "").strip()
    try:
        info = await cards.mono_client_info(token)
    except Exception as ex:
        raise HTTPException(400, f"Monobank did not accept the token: {str(ex)[:120]}")
    accounts = info.get("accounts", [])
    acc = next((a for a in accounts if a.get("id") == body.get("account")), None) or \
        next((a for a in accounts if a.get("currencyCode") == 980 and a.get("maskedPan")), None)
    if not acc:
        raise HTTPException(400, "No hryvnia card found on this Monobank account")
    await cards.mono_set_webhook(token, f"{config.PUBLIC_URL}/hooks/mono/{c['hook_secret']}")
    label = f"Monobank {acc.get('type', '')} •• {(acc.get('maskedPan') or ['????'])[0][-4:]}"
    store.set_campaign(c["id"], card_mode="monobank", mono_token=token, mono_account=acc["id"], card_label=label)
    store.log(c["id"], "note", f"💳 Transparent card linked: {label} (read-only bank feed)")
    return {"card_label": label}


@app.get("/hooks/mono/{secret}")
async def mono_hook_check(secret: str):
    return {"ok": True}  # Monobank validates the URL with a GET before sending events


@app.post("/hooks/mono/{secret}")
async def mono_hook(secret: str, request: Request):
    c = store.campaign_by_hook(secret)
    body = await request.json()
    if c and body.get("type") == "StatementItem" and body["data"].get("account") == c["mono_account"]:
        # Monobank wants 200 within 5 s; the audit runs after we answer
        asyncio.create_task(service.card_payment(c["id"], cards.from_mono(body["data"]["statementItem"])))
    return {"ok": True}


# ---------- volunteer: evidence ----------

JOBS: dict[str, dict] = {}  # audit jobs the page polls: id -> {events, done, result, error}


@app.post("/api/tranches/{tid}/evidence")
async def api_evidence(tid: str, code: str = Form(...), photo: UploadFile = File(...),
                       receipt: UploadFile | None = File(None)):
    """Starts the audit of a tranche's evidence and returns a job id; the page polls /api/jobs/{id} for every check."""
    t = store.tranche(tid)
    c = _volunteer(code)
    if not t or t["campaign_id"] != c["id"]:
        raise HTTPException(403, "This tranche is not in your campaign")
    p = await photo.read()
    r = await receipt.read() if receipt else None
    if len(p) > 12_000_000 or (r and len(r) > 12_000_000):
        raise HTTPException(413, "Image too large (max 12 MB)")
    try:
        service.check_tranche(tid)
    except ValueError as ex:
        raise HTTPException(400, str(ex))
    job_id = uuid.uuid4().hex[:12]
    job = JOBS[job_id] = {"events": [], "done": False, "result": None, "error": None, "started": time.time()}

    async def step(event: dict):
        event["t"] = round(time.time() - job["started"], 1)
        job["events"].append(event)

    async def run():
        try:
            v = await service.submit_evidence(tid, p, r or None, "website", step)
            job["result"] = {k: v.get(k) for k in ("decision", "accounted", "photo_ok", "spent", "summary", "reasons",
                                                   "message_to_volunteer", "checks", "files")}
            if v.get("released"):
                job["result"]["released"] = {k: v["released"][k] for k in ("title", "amount")}
        except Exception as ex:
            log.exception("evidence")
            job["error"] = str(ex)[:300]
        job["done"] = True

    asyncio.create_task(run())
    for old in sorted(JOBS, key=lambda k: JOBS[k]["started"])[:-50]:
        JOBS.pop(old, None)
    return {"job": job_id}


@app.get("/api/jobs/{job_id}")
async def api_job(job_id: str, after: int = 0):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404)
    return {"events": job["events"][after:], "done": job["done"], "result": job["result"], "error": job["error"]}


# ---------- refunds and resets ----------

@app.post("/api/campaigns/{cid}/fail")
async def api_fail(cid: str, body: dict):
    c = store.campaign(cid)
    if not c:
        raise HTTPException(404)
    key = body.get("code", "")
    if not (key and (key.upper() == c["volunteer_code"] or (ADMIN_KEY and key == ADMIN_KEY))):
        raise HTTPException(403, "Volunteer code needed")
    if c["status"] in ("refunded", "completed"):
        raise HTTPException(400, f"This campaign is already {c['status']}")
    return await service.refund_campaign(cid, body.get("reason") or "the volunteer did not account for the money")


@app.post("/api/campaigns/{cid}/reset")
async def api_reset_try(cid: str):
    try:
        await service.reset_try_campaign(cid)
    except ValueError as ex:
        raise HTTPException(400, str(ex))
    return {"ok": True}


@app.post("/api/demo/reset")
async def api_reset(body: dict):
    if not ADMIN_KEY or body.get("key") != ADMIN_KEY:
        raise HTTPException(403)
    seed.seed(wipe=True)
    return {"ok": True}


app.mount("/uploads", StaticFiles(directory=str(config.UPLOAD_DIR), check_dir=False), name="uploads")
app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")
