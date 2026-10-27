"""The AI auditor: what a tranche's money bought, proven by the bank feed of the volunteer's card, a photo of the
item delivered and, for a bank line that does not say what was bought, a receipt.

Every check is reported live through `on_step`, so the site and the bot show the audit as it runs:
  1. bank feed      card payments already classified on arrival (matched / unclear / flagged), money spent
  2. file facts     sha256 and perceptual hash (picture reused), EXIF capture date and software, C2PA credentials
  3. Gemini         looks at the photo (the item? a real on-site photo?) and reads the receipt, in parallel
  4. receipt        its total must equal an unclear card payment to explain it
  5. verdict        Gemini weighs everything and writes the public explanation; hard failures override it
"""
import asyncio
import base64
import datetime as dt
import hashlib
import io
import json
import time
from typing import Awaitable, Callable

import httpx
import imagehash
from PIL import ExifTags, Image

from . import config

Step = Callable[[dict], Awaitable[None]] | None

# ---------- file facts ----------

def _ratio(v) -> float:
    try:
        return float(v)
    except Exception:
        return float(v[0]) / float(v[1])


def _gps(gps: dict) -> dict | None:
    try:
        def dms(x, ref):
            d, m, s = (_ratio(v) for v in x)
            val = d + m / 60 + s / 3600
            return -val if ref in ("S", "W") else val
        return {"lat": round(dms(gps[2], gps[1]), 5), "lon": round(dms(gps[4], gps[3]), 5)}
    except Exception:
        return None


def file_facts(data: bytes) -> dict:
    """sha256, phash, size, EXIF (date, camera, software, GPS), C2PA presence."""
    facts = {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
    img = Image.open(io.BytesIO(data))
    facts["size"] = f"{img.width}x{img.height}"
    facts["format"] = img.format
    facts["phash"] = str(imagehash.phash(img))
    exif = {}
    try:
        raw = img.getexif()
        for tag, val in raw.items():
            exif[ExifTags.TAGS.get(tag, str(tag))] = val
        ifd = raw.get_ifd(ExifTags.IFD.Exif)
        for tag, val in ifd.items():
            exif[ExifTags.TAGS.get(tag, str(tag))] = val
        gps = raw.get_ifd(ExifTags.IFD.GPSInfo)
        if gps:
            facts["gps"] = _gps(dict(gps))
    except Exception:
        pass
    taken = exif.get("DateTimeOriginal") or exif.get("DateTime")
    if taken:
        try:
            facts["taken"] = dt.datetime.strptime(str(taken)[:19], "%Y:%m:%d %H:%M:%S").isoformat()
        except ValueError:
            facts["taken_raw"] = str(taken)
    for key in ("Make", "Model", "Software"):
        if exif.get(key):
            facts[key.lower()] = str(exif[key]).strip("\x00 ")
    facts["has_exif"] = bool(taken or exif.get("Make"))
    facts["c2pa"] = _c2pa(data)
    return facts


def _c2pa(data: bytes) -> dict | None:
    """Content Credentials (C2PA) manifest summary, if the file carries one."""
    try:
        import c2pa  # optional
        reader = c2pa.Reader("image/jpeg", io.BytesIO(data))
        manifest = json.loads(reader.json())
        active = manifest.get("manifests", {}).get(manifest.get("active_manifest", ""), {})
        gen = active.get("claim_generator_info") or [{}]
        return {"present": True, "generator": gen[0].get("name", ""), "title": active.get("title", "")}
    except Exception:
        return None


# ---------- exchange rates (National Bank of Ukraine, free, no key) ----------

_rates: dict[str, tuple[float, float]] = {}


async def uah_rate(code: str) -> float:
    """How many UAH one unit of `code` costs today (USD -> ~41)."""
    code = code.upper()
    if code == "UAH":
        return 1.0
    cached = _rates.get(code)
    if cached and time.time() - cached[1] < 6 * 3600:
        return cached[0]
    async with httpx.AsyncClient(timeout=20) as http:
        r = await http.get(config.NBU_API, params={"valcode": code, "json": ""})
        r.raise_for_status()
        rate = float(r.json()[0]["rate"])
    _rates[code] = (rate, time.time())
    return rate


async def convert(amount: float, src: str, dst: str) -> float:
    if src.upper() == dst.upper():
        return round(amount, 2)
    return round(amount * await uah_rate(src) / await uah_rate(dst), 2)


# ---------- Gemini ----------

async def _generate(parts: list[dict], schema: dict) -> dict:
    body = {"contents": [{"role": "user", "parts": parts}],
            "generationConfig": {"temperature": 0.1, "responseMimeType": "application/json",
                                 "responseSchema": schema, "thinkingConfig": {"thinkingLevel": "low"}}}
    headers = {"x-goog-api-key": config.secret("GEMINI_API_KEY")}
    errors = []
    async with httpx.AsyncClient(timeout=60) as http:
        for model in config.GEMINI_MODELS:
            try:
                r = await http.post(f"{config.GEMINI_API}/models/{model}:generateContent", json=body, headers=headers)
            except httpx.TimeoutException:
                errors.append(f"{model} timeout")
                continue
            if r.status_code == 200:
                return json.loads(r.json()["candidates"][0]["content"]["parts"][0]["text"])
            errors.append(f"{model} {r.status_code}: {r.text[:160]}")
            if r.status_code not in (429, 500, 503, 404):
                break
    raise RuntimeError("Gemini failed — " + " | ".join(errors))


def _img(data: bytes, mime: str = "image/jpeg") -> dict:
    return {"inline_data": {"mime_type": mime, "data": base64.b64encode(data).decode()}}


RECEIPT_SCHEMA = {"type": "OBJECT", "properties": {
    "is_receipt": {"type": "BOOLEAN"},
    "store": {"type": "STRING"},
    "items": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
        "name": {"type": "STRING"}, "quantity": {"type": "NUMBER"}, "price": {"type": "NUMBER"}},
        "required": ["name", "quantity", "price"]}},
    "total": {"type": "NUMBER"},
    "currency": {"type": "STRING"},
    "date": {"type": "STRING"},
    "looks_real": {"type": "BOOLEAN"},
    "concerns": {"type": "ARRAY", "items": {"type": "STRING"}},
}, "required": ["is_receipt", "store", "items", "total", "currency", "date", "looks_real", "concerns"]}

PHOTO_SCHEMA = {"type": "OBJECT", "properties": {
    "description": {"type": "STRING"},
    "objects": {"type": "ARRAY", "items": {"type": "STRING"}},
    "setting": {"type": "STRING"},
    "shows_item": {"type": "BOOLEAN"},
    "item_explanation": {"type": "STRING"},
    "visible_brand_or_model": {"type": "STRING"},
    "is_screenshot_or_stock_or_ai": {"type": "BOOLEAN"},
    "concerns": {"type": "ARRAY", "items": {"type": "STRING"}},
}, "required": ["description", "objects", "setting", "shows_item", "item_explanation", "visible_brand_or_model",
                "is_screenshot_or_stock_or_ai", "concerns"]}

VERDICT_SCHEMA = {"type": "OBJECT", "properties": {
    "decision": {"type": "STRING", "enum": ["approve", "reject", "review"]},
    "confidence": {"type": "NUMBER"},
    "photo_matches_purchase": {"type": "BOOLEAN"},
    "summary_for_donors": {"type": "STRING"},
    "reasons": {"type": "ARRAY", "items": {"type": "STRING"}},
    "message_to_volunteer": {"type": "STRING"},
}, "required": ["decision", "confidence", "photo_matches_purchase", "summary_for_donors", "reasons",
                "message_to_volunteer"]}


async def read_receipt(data: bytes) -> dict:
    prompt = (f"You are an auditor for a donation platform. Today is {dt.date.today().isoformat()}. "
              "Read this receipt or invoice photo carefully. "
              "Return the store, each item with quantity and price, the total, the currency (ISO code; Ukrainian "
              "receipts are UAH, '₴' or 'грн'), the date (ISO YYYY-MM-DD if readable), whether it looks like a "
              "real printed or fiscal receipt (not an edited image or a mock-up), and any concerns.")
    return await _generate([{"text": prompt}, _img(data)], RECEIPT_SCHEMA)


async def inspect_photo(data: bytes, tranche_title: str, place: str) -> dict:
    prompt = (f"You are an auditor for a donation platform. A volunteer claims this photo shows what was bought "
              f"for '{tranche_title}', delivered in {place}. Describe the photo, list the objects, describe the "
              f"setting, say whether that item is really visible (shows_item), quote any brand or model you can "
              f"read, and say whether the picture looks like a screenshot, a stock or catalogue image or an AI "
              f"render instead of a phone photo taken on site.")
    return await _generate([{"text": prompt}, _img(data)], PHOTO_SCHEMA)


async def decide(context: dict) -> dict:
    prompt = (f"Today is {dt.date.today().isoformat()}. "
              "You are the final auditor of Proof of Good. Donated money for one tranche was sent to the volunteer's "
              "dedicated card; the bank shows every payment from that card. Now the volunteer shows a photo of the "
              "item delivered (and a receipt when a bank line did not say what was bought). Weigh the evidence below. "
              "Set photo_matches_purchase: does the photo show what the card payments bought (same kind, and the same "
              "brand/model where readable)? Decide: approve (the money bought the purpose and the photo shows it "
              "delivered), reject (fake or reused photo, wrong item, fraud), or review (unclear, a human should "
              "look). Missing EXIF alone is not fraud (messengers strip it). Write summary_for_donors as one warm "
              "English sentence telling donors what their money bought and where. Write message_to_volunteer in "
              "English: what passed, what is missing (unspent money, an unclear payment without a receipt, a better "
              "photo).\n\nEvidence:\n" + json.dumps(context, ensure_ascii=False, default=str))
    return await _generate([{"text": prompt}], VERDICT_SCHEMA)


# ---------- the audit of a tranche's evidence ----------

async def audit_evidence(tranche: dict, campaign: dict, txs: list[dict], photo_bytes: bytes,
                         receipt_bytes: bytes | None, known_phashes: list[tuple[str, str, str]], known_shas: set[str],
                         on_step: Step = None) -> dict:
    """Card payments + delivery photo (+ a receipt for unclear payments) -> {decision, photo_ok, accounted, ...}."""
    checks: list[dict] = []
    hard_fail = False

    async def emit(**event):
        if on_step:
            await on_step(event)

    async def check(name: str, ok: bool | None, detail: str, hard: bool = False):
        nonlocal hard_fail
        checks.append({"name": name, "ok": ok, "detail": detail})
        if ok is False and hard:
            hard_fail = True
        await emit(kind="check", name=name, ok=ok, detail=detail)

    cur = campaign["currency"]
    # 1. what the bank says
    await emit(kind="stage", name="Reading the card's bank feed")
    matched = [t for t in txs if t["status"] == "matched"]
    unclear = [t for t in txs if t["status"] == "unclear"]
    flagged = [t for t in txs if t["status"] == "flagged"]
    spent = round(sum(t["usd"] or 0 for t in matched), 2)
    if not txs:
        await check("card payments", None, "no payments from the card for this tranche yet")
    for t in txs:
        mark = {"matched": True, "unclear": None, "flagged": False}.get(t["status"])
        await check(f"card: {t['description']}", mark,
                    f"{abs(t['amount']):,.0f} {t['currency']} ≈ {t['usd']:.2f} {cur} — {t['reason']}")
    if flagged:
        await check("no money left the purpose", False, f"{len(flagged)} flagged payment(s) on this tranche", True)

    # 2. the files
    await emit(kind="stage", name="Fingerprinting the photo" + (" and the receipt" if receipt_bytes else ""))
    pf = file_facts(photo_bytes)
    rf = file_facts(receipt_bytes) if receipt_bytes else None
    for label, f in (("photo", pf), ("receipt", rf)):
        if not f:
            continue
        if f["sha256"] in known_shas:
            await check(f"{label}: unique file", False, "this exact file was already used as proof", True)
        else:
            near = [d for d in (imagehash.hex_to_hash(f["phash"]) - imagehash.hex_to_hash(h) for h, _, _ in known_phashes)
                    if d <= config.PHASH_SAME]
            await check(f"{label}: not reused", not near,
                        "looks like a picture already used as proof" if near else "no match among stored proofs", True)
        if f.get("taken"):
            taken = dt.datetime.fromisoformat(f["taken"])
            since = dt.datetime.fromtimestamp(tranche.get("released_at") or campaign["created"]) - dt.timedelta(hours=12)
            await check(f"{label}: taken after the money was released", taken >= since,
                        f"shot {taken:%Y-%m-%d %H:%M}", label == "photo")
        else:
            await check(f"{label}: capture date", None, "no camera metadata (sent compressed?)")
        if f.get("software"):
            edited = any(k in f["software"].lower() for k in ("photoshop", "gimp", "lightroom", "snapseed", "canva"))
            await check(f"{label}: not edited", not edited, f"software: {f['software']}")
        if f.get("c2pa"):
            gen = (f["c2pa"].get("generator") or "").lower()
            ai = any(k in gen for k in ("openai", "dall", "firefly", "midjourney", "gemini", "imagen", "stable"))
            await check(f"{label}: content credentials", False if ai else None,
                        f"C2PA by {f['c2pa'].get('generator') or '?'}" + (" — an AI generator" if ai else ""), hard=ai)

    # 3. the photo (and the receipt) through Gemini, in parallel
    await emit(kind="stage", name="Looking at the photo" + (" and reading the receipt" if receipt_bytes else ""))
    jobs = [inspect_photo(photo_bytes, tranche["title"], campaign["place"])]
    if receipt_bytes:
        jobs.append(read_receipt(receipt_bytes))
    got = await asyncio.gather(*jobs)
    photo, receipt = got[0], (got[1] if receipt_bytes else None)
    await check("photo: shows the item", photo["shows_item"], photo["item_explanation"], True)
    await check("photo: real on-site photo", not photo["is_screenshot_or_stock_or_ai"],
                "; ".join(photo["concerns"]) or photo["setting"], True)

    # 4. a receipt settles an unclear bank line when its total is the same money
    matched_tx = []
    if receipt is not None:
        if not receipt["is_receipt"]:
            await check("receipt: readable", False, "the picture is not a receipt", True)
        else:
            await check("receipt: looks genuine", receipt["looks_real"], "; ".join(receipt["concerns"]) or
                        f"{receipt['store']} — {receipt['total']:,.2f} {receipt['currency']}")
            for t in unclear:
                if receipt["currency"].upper() == t["currency"].upper() and \
                        abs(receipt["total"] - abs(t["amount"])) <= max(1.0, abs(t["amount"]) * 0.02):
                    items = ", ".join(i["name"] for i in receipt["items"][:3])
                    await check(f"receipt explains «{t['description']}»", True,
                                f"{receipt['total']:,.2f} {receipt['currency']} = the card payment; items: {items}")
                    matched_tx.append(t["id"])
                    spent = round(spent + (t["usd"] or 0), 2)
                    break
            else:
                if unclear:
                    await check("receipt matches a card payment", False,
                                f"receipt {receipt['total']:,.2f} {receipt['currency']} ≠ any unclear payment")
    still_unclear = [t for t in unclear if t["id"] not in matched_tx]
    if still_unclear:
        await check("every payment explained", False,
                    f"{len(still_unclear)} payment(s) need a receipt: " + ", ".join(t["description"] for t in still_unclear))

    # 5. money spent vs the tranche
    enough = spent >= tranche["amount"] * config.SPEND_MIN
    await check("the tranche is spent", enough, f"{spent:.2f} of {tranche['amount']:.2f} {cur} spent in matched payments")

    # 6. verdict
    await emit(kind="stage", name="Weighing the evidence")
    context = {"tranche": {"title": tranche["title"], "amount": tranche["amount"], "currency": cur},
               "campaign": {"title": campaign["title"], "place": campaign["place"]},
               "card_payments": [{k: t[k] for k in ("description", "mcc", "amount", "currency", "usd", "status", "reason")}
                                 for t in txs],
               "checks": checks, "photo": photo, "receipt": receipt,
               "photo_file": {k: pf.get(k) for k in ("taken", "make", "model", "software", "gps", "has_exif")}}
    verdict = await decide(context)
    if photo["shows_item"] and (matched or matched_tx):
        await check("photo matches the purchase", verdict["photo_matches_purchase"],
                    f"photo: {photo['visible_brand_or_model'] or photo['description'][:80]}", True)
    if hard_fail and verdict["decision"] == "approve":
        verdict["decision"] = "reject"
        verdict["reasons"].insert(0, "a hard check failed")
    photo_ok = not hard_fail and photo["shows_item"] and not photo["is_screenshot_or_stock_or_ai"] and \
        verdict["decision"] != "reject"
    accounted = photo_ok and enough and not still_unclear and not flagged
    result = {"decision": verdict["decision"], "confidence": verdict["confidence"], "photo_ok": photo_ok,
              "accounted": accounted, "spent": spent, "matched_tx": matched_tx,
              "summary": verdict["summary_for_donors"], "reasons": verdict["reasons"],
              "message_to_volunteer": verdict["message_to_volunteer"], "checks": checks,
              "failed": [c["name"] for c in checks if c["ok"] is False], "photo": photo, "receipt": receipt,
              "photo_facts": pf, "receipt_facts": rf, "at": time.time()}
    await emit(kind="verdict", decision=result["decision"], accounted=accounted, summary=result["summary"],
               message=result["message_to_volunteer"])
    return result
