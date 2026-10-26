"""The AI auditor: receipt + photo + metadata -> verdict on a tranche.

Checks, in order:
  1. file facts     sha256 (exact duplicate), perceptual hash (same picture reused), EXIF date / GPS / software,
                    C2PA content credentials when present
  2. receipt        Gemini reads store, items, total, currency, date; says if it looks like a real printed receipt
  3. money          total converted to the campaign currency with the National Bank of Ukraine rate,
                    compared with the planned tranche amount
  4. photo          Gemini describes what is in the picture, whether it is the item from the receipt and whether
                    it looks like a screenshot, a stock image or an AI render
  5. verdict        Gemini weighs everything and writes the public explanation; hard failures override it
"""
import base64
import datetime as dt
import hashlib
import io
import json
import time

import httpx
import imagehash
from PIL import ExifTags, Image

from . import config

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
    "matches_receipt": {"type": "BOOLEAN"},
    "match_explanation": {"type": "STRING"},
    "is_screenshot_or_stock_or_ai": {"type": "BOOLEAN"},
    "concerns": {"type": "ARRAY", "items": {"type": "STRING"}},
}, "required": ["description", "objects", "setting", "matches_receipt", "match_explanation",
                "is_screenshot_or_stock_or_ai", "concerns"]}

VERDICT_SCHEMA = {"type": "OBJECT", "properties": {
    "decision": {"type": "STRING", "enum": ["approve", "reject", "review"]},
    "confidence": {"type": "NUMBER"},
    "summary_for_donors": {"type": "STRING"},
    "reasons": {"type": "ARRAY", "items": {"type": "STRING"}},
    "message_to_volunteer": {"type": "STRING"},
}, "required": ["decision", "confidence", "summary_for_donors", "reasons", "message_to_volunteer"]}


async def read_receipt(data: bytes) -> dict:
    prompt = (f"You are an auditor for a donation platform. Today is {dt.date.today().isoformat()}. "
              "Read this receipt or invoice photo carefully. "
              "Return the store, each item with quantity and price, the total, the currency (ISO code; Ukrainian "
              "receipts are UAH, '₴' or 'грн'), the date (ISO YYYY-MM-DD if readable), whether it looks like a "
              "real printed or fiscal receipt (not an edited image or a mock-up), and any concerns.")
    return await _generate([{"text": prompt}, _img(data)], RECEIPT_SCHEMA)


async def inspect_photo(data: bytes, receipt: dict, tranche_title: str, place: str) -> dict:
    prompt = (f"You are an auditor for a donation platform. A volunteer claims this photo shows the purchased "
              f"item(s) delivered for the tranche '{tranche_title}' in {place}. The receipt lists: "
              f"{json.dumps(receipt.get('items', []), ensure_ascii=False)} from {receipt.get('store', '?')}. "
              f"Describe the photo, list the objects, describe the setting, say whether the item from the receipt "
              f"is really visible (same kind, brand or model where readable), and whether the picture looks like "
              f"a screenshot, a stock or catalogue image, or an AI render instead of a phone photo taken on site.")
    return await _generate([{"text": prompt}, _img(data)], PHOTO_SCHEMA)


async def decide(context: dict) -> dict:
    prompt = (f"Today is {dt.date.today().isoformat()}. "
              "You are the final auditor of Proof of Good, a platform where donated money is released to a "
              "volunteer only when proof of the purchase is convincing. Weigh all the evidence below and decide: "
              "approve (release the money), reject (clear signs of fraud or wrong item), or review (unclear, a "
              "human should look). Be fair to honest volunteers: a receipt total within the tolerance, a matching "
              "photo and plausible metadata should be approved; missing EXIF alone is not fraud (messengers strip "
              "it). Write summary_for_donors as one warm sentence in English telling donors what their money "
              "bought (name the item and the place). Write message_to_volunteer in English: what passed, what to "
              "fix if anything.\n\nEvidence:\n" + json.dumps(context, ensure_ascii=False, default=str))
    return await _generate([{"text": prompt}], VERDICT_SCHEMA)


# ---------- the audit ----------

async def audit(tranche: dict, campaign: dict, receipt_bytes: bytes, photo_bytes: bytes,
                known_phashes: list[tuple[str, str, str]], known_shas: set[str]) -> dict:
    """Runs every check and returns {decision, reasons, checks, receipt, photo, facts, money, summary...}."""
    checks: list[dict] = []
    hard_fail = False

    def check(name: str, ok: bool | None, detail: str, hard: bool = False):
        nonlocal hard_fail
        checks.append({"name": name, "ok": ok, "detail": detail})
        if ok is False and hard:
            hard_fail = True

    rf, pf = file_facts(receipt_bytes), file_facts(photo_bytes)

    # 1. duplicates and reuse
    for label, f in (("receipt", rf), ("photo", pf)):
        if f["sha256"] in known_shas:
            check(f"{label}: unique file", False, "this exact file was already submitted for another tranche", True)
        else:
            near = [(imagehash.hex_to_hash(f["phash"]) - imagehash.hex_to_hash(h), pid) for h, pid, _ in known_phashes]
            near = [x for x in near if x[0] <= config.PHASH_SAME]
            if near:
                check(f"{label}: not reused", False, f"looks like a picture already used as proof ({near[0][1]})", True)
            else:
                check(f"{label}: not reused", True, "no match among stored proofs")

    # 2. metadata
    created = dt.datetime.fromtimestamp(campaign["created"])
    for label, f in (("receipt", rf), ("photo", pf)):
        if f.get("taken"):
            taken = dt.datetime.fromisoformat(f["taken"])
            if taken < created - dt.timedelta(days=1):
                check(f"{label}: taken after the campaign started", False,
                      f"shot {taken:%Y-%m-%d}, campaign started {created:%Y-%m-%d}", True)
            elif taken > dt.datetime.now() + dt.timedelta(days=1):
                check(f"{label}: date plausible", False, f"camera date {taken:%Y-%m-%d} is in the future")
            else:
                check(f"{label}: taken after the campaign started", True, f"shot {taken:%Y-%m-%d %H:%M}")
        else:
            check(f"{label}: capture date", None, "no camera metadata (sent compressed?)")
        if f.get("software"):
            edited = any(k in f["software"].lower() for k in ("photoshop", "gimp", "lightroom", "snapseed", "canva"))
            check(f"{label}: not edited", not edited, f"software: {f['software']}")
        if f.get("gps"):
            check(f"{label}: location", None, f"GPS {f['gps']['lat']}, {f['gps']['lon']}")
        if f.get("c2pa"):
            check(f"{label}: content credentials", None, f"C2PA by {f['c2pa'].get('generator') or '?'}")

    # 3. receipt
    receipt = await read_receipt(receipt_bytes)
    if not receipt["is_receipt"]:
        check("receipt: readable", False, "the picture is not a receipt", True)
    else:
        check("receipt: readable", True, f"{receipt['store']}, {len(receipt['items'])} item(s), "
                                         f"{receipt['total']:.2f} {receipt['currency']}, {receipt['date'] or 'no date'}")
        check("receipt: looks genuine", receipt["looks_real"], "; ".join(receipt["concerns"]) or "no concerns")
        if receipt.get("date"):
            try:
                rd = dt.date.fromisoformat(receipt["date"][:10])
                check("receipt: dated after the campaign started", rd >= created.date() - dt.timedelta(days=1),
                      f"receipt {rd}, campaign started {created:%Y-%m-%d}", True)
            except ValueError:
                pass

    # 4. money
    money = {}
    if receipt["is_receipt"] and receipt["total"]:
        try:
            paid = await convert(receipt["total"], receipt["currency"], campaign["currency"])
            money = {"receipt_total": receipt["total"], "receipt_currency": receipt["currency"],
                     "converted": paid, "currency": campaign["currency"], "tranche": tranche["amount"],
                     "rate_source": "National Bank of Ukraine"}
            diff = (paid - tranche["amount"]) / tranche["amount"]
            check("amount matches the tranche", abs(diff) <= config.AMOUNT_TOLERANCE,
                  f"receipt {paid:.2f} {campaign['currency']} vs planned {tranche['amount']:.2f} ({diff:+.0%})",
                  hard=diff > config.AMOUNT_TOLERANCE * 2 or diff < -0.5)
        except Exception as ex:
            check("amount matches the tranche", None, f"could not convert: {ex}")

    # 5. photo
    photo = await inspect_photo(photo_bytes, receipt, tranche["title"], campaign["place"])
    check("photo: shows the purchased item", photo["matches_receipt"], photo["match_explanation"], True)
    check("photo: real on-site photo", not photo["is_screenshot_or_stock_or_ai"],
          "; ".join(photo["concerns"]) or photo["setting"], True)

    # 6. verdict
    context = {"tranche": {"title": tranche["title"], "amount": tranche["amount"], "currency": campaign["currency"]},
               "campaign": {"title": campaign["title"], "place": campaign["place"]},
               "checks": checks, "receipt": receipt, "photo": photo, "money": money,
               "receipt_file": {k: rf.get(k) for k in ("taken", "make", "model", "software", "gps", "has_exif")},
               "photo_file": {k: pf.get(k) for k in ("taken", "make", "model", "software", "gps", "has_exif")}}
    verdict = await decide(context)
    if hard_fail and verdict["decision"] == "approve":
        verdict["decision"] = "reject"
        verdict["reasons"].insert(0, "a hard check failed")
    failed = [c for c in checks if c["ok"] is False]
    return {"decision": verdict["decision"], "confidence": verdict["confidence"],
            "summary": verdict["summary_for_donors"], "reasons": verdict["reasons"],
            "message_to_volunteer": verdict["message_to_volunteer"], "checks": checks,
            "failed": [c["name"] for c in failed], "receipt": receipt, "photo": photo, "money": money,
            "receipt_facts": rf, "photo_facts": pf, "at": time.time()}
