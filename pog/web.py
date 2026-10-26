"""The website: campaign pages with PayPal donate buttons, the volunteer portal, the public ledger, JSON API."""
import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config, seed, service, store

log = logging.getLogger("pog.web")
STATIC = Path(__file__).resolve().parent.parent / "static"
ADMIN_KEY = os.environ.get("ADMIN_KEY", "")


@asynccontextmanager
async def lifespan(app: FastAPI):
    seed.seed()
    config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    tasks = [asyncio.create_task(_housekeeping())]
    if os.environ.get("RUN_BOT", "1") == "1":
        from . import bot
        tasks.append(asyncio.create_task(bot.run_in_background()))
    yield
    for t in tasks:
        t.cancel()


async def _housekeeping():
    while True:
        try:
            await service.refresh_payouts()
        except Exception:
            log.exception("housekeeping")
        await asyncio.sleep(120)


app = FastAPI(title="Proof of Good", lifespan=lifespan)


def _tranche_view(t: dict) -> dict:
    v = json.loads(t["verdict"]) if t.get("verdict") else None
    out = {k: t[k] for k in ("id", "position", "title", "amount", "status", "paid_batch", "paid_at")}
    if v:
        out["verdict"] = {k: v.get(k) for k in ("decision", "confidence", "summary", "reasons", "checks", "money",
                                                 "files", "via", "at")}
    out["proofs"] = [{"kind": p["kind"], "file": p["file"], "meta": json.loads(p["meta"] or "{}")}
                     for p in store.proofs(t["id"])]
    return out


def _campaign_view(c: dict, full: bool = False) -> dict:
    out = {k: c[k] for k in ("id", "title", "story", "place", "country", "volunteer_name", "currency", "status",
                             "created", "cover")}
    out["totals"] = store.totals(c["id"])
    out["tranches"] = [_tranche_view(t) for t in store.tranches(c["id"])]
    if full:
        out["ledger"] = store.ledger(c["id"])
        out["donations"] = [{"name": d["donor_name"] or "Anonymous", "amount": d["amount"], "status": d["status"],
                             "created": d["created"]} for d in store.donations(c["id"])]
    return out


# ---------- pages ----------

@app.api_route("/", methods=["GET", "HEAD"])
async def page_index():
    return FileResponse(STATIC / "index.html")


@app.api_route("/healthz", methods=["GET", "HEAD"])
async def healthz():
    return {"ok": True}


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


# ---------- api ----------

@app.get("/api/config")
async def api_config():
    return {"paypal_client_id": config.secret("PAYPAL_CLIENT_ID"), "currency": "USD",
            "sandbox": "sandbox" in config.PAYPAL_API, "public_url": config.PUBLIC_URL,
            "sandbox_buyer": os.environ.get("SANDBOX_BUYER", ""),
            "bot": os.environ.get("BOT_USERNAME", "")}


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


@app.post("/api/volunteer/login")
async def api_volunteer_login(body: dict):
    c = store.campaign_by_code(body.get("code", ""))
    if not c:
        raise HTTPException(404, "No campaign with this code")
    return _campaign_view(c, full=True)


@app.post("/api/tranches/{tid}/proof")
async def api_proof(tid: str, code: str = Form(...), receipt: UploadFile = File(...), photo: UploadFile = File(...)):
    t = store.tranche(tid)
    c = store.campaign(t["campaign_id"]) if t else None
    if not c or c["volunteer_code"] != code.strip().upper():
        raise HTTPException(403, "Wrong volunteer code")
    r, p = await receipt.read(), await photo.read()
    if len(r) > 12_000_000 or len(p) > 12_000_000:
        raise HTTPException(413, "Image too large (max 12 MB)")
    try:
        v = await service.submit_proof(tid, r, p, "website")
    except ValueError as ex:
        raise HTTPException(400, str(ex))
    except Exception as ex:
        log.exception("proof")
        raise HTTPException(500, f"Audit failed: {str(ex)[:200]}")
    return {k: v.get(k) for k in ("decision", "confidence", "summary", "reasons", "message_to_volunteer", "checks",
                                  "money", "files", "paid")}


@app.post("/api/campaigns/{cid}/fail")
async def api_fail(cid: str, body: dict):
    c = store.campaign(cid)
    if not c:
        raise HTTPException(404)
    key = body.get("code", "")
    if not (key and (key.upper() == c["volunteer_code"] or (ADMIN_KEY and key == ADMIN_KEY))):
        raise HTTPException(403, "Volunteer code needed")
    return await service.refund_campaign(cid, body.get("reason") or "deadline passed without proof")


@app.post("/api/demo/reset")
async def api_reset(body: dict):
    if not ADMIN_KEY or body.get("key") != ADMIN_KEY:
        raise HTTPException(403)
    seed.seed(wipe=True)
    return {"ok": True}


@app.get("/api/ledger")
async def api_ledger():
    titles = {c["id"]: c["title"] for c in store.campaigns()}
    rows = store.ledger()
    for r in rows:
        r["campaign"] = titles.get(r["campaign_id"], r["campaign_id"])
    return rows


@app.get("/api/uah")
async def api_rate():
    from . import audit
    return {"USD": await audit.uah_rate("USD"), "source": "National Bank of Ukraine"}


app.mount("/uploads", StaticFiles(directory=str(config.UPLOAD_DIR), check_dir=False), name="uploads")
app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")
