"""What happens with the money: donations in, proofs audited, tranches paid out, failed campaigns refunded.
Shared by the website and the Telegram bot."""
import html
import logging
import time

from . import audit, config, notify, store
from .paypal import PayPal, PayPalError

log = logging.getLogger("pog.service")
paypal = PayPal()


def money(amount: float, currency: str = "USD") -> str:
    return f"${amount:,.2f}" if currency == "USD" else f"{amount:,.2f} {currency}"


# ---------- donations ----------

async def start_donation(cid: str, amount: float) -> str:
    c = store.campaign(cid)
    if not c or c["status"] != "active":
        raise ValueError("campaign is not accepting donations")
    if not 1 <= amount <= 10000:
        raise ValueError("amount must be between 1 and 10 000")
    order = await paypal.create_order(amount, c["currency"], f"Donation: {c['title']}", cid)
    return order["id"]


async def finish_donation(order_id: str) -> dict:
    order = await paypal.get_order(order_id)
    cid = order["purchase_units"][0]["reference_id"]
    c = store.campaign(cid)
    cap = await paypal.capture_order(order_id)
    store.add_donation({"id": cap["capture_id"], "campaign_id": cid, "order_id": order_id,
                        "donor_name": cap["payer_name"], "donor_email": cap["payer_email"],
                        "amount": cap["amount"], "currency": cap["currency"]})
    who = cap["payer_name"] or "Someone"
    store.log(cid, "donation", f"{who} donated {money(cap['amount'], cap['currency'])} — held until proof",
              cap["amount"], cap["capture_id"])
    totals = store.totals(cid)
    await notify.send(c["volunteer_chat"],
                      f"💙 {html.escape(who)} donated <b>{money(cap['amount'])}</b> to «{html.escape(c['title'])}». "
                      f"Raised {money(totals['raised'])} of {money(totals['goal'])}.")
    # a verified tranche may have been waiting for money
    await _pay_verified(cid)
    return {"donation": cap, "totals": totals}


# ---------- proofs ----------

async def submit_proof(tid: str, receipt: bytes, photo: bytes, via: str) -> dict:
    t = store.tranche(tid)
    c = store.campaign(t["campaign_id"]) if t else None
    if not t or not c:
        raise ValueError("unknown tranche")
    if t["status"] == "paid":
        raise ValueError("this tranche is already paid")
    if c["status"] != "active":
        raise ValueError("this campaign is closed")
    store.set_tranche(tid, status="checking")
    try:
        v = await audit.audit(t, c, receipt, photo, store.all_phashes(tid), store.all_shas(tid))
    except Exception:
        store.set_tranche(tid, status=t["status"] if t["status"] != "checking" else "waiting")
        raise
    files = {}
    for kind, data, facts in (("receipt", receipt, v["receipt_facts"]), ("photo", photo, v["photo_facts"])):
        name = f"{tid}_{int(time.time())}_{kind}.jpg"
        config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        (config.UPLOAD_DIR / name).write_bytes(data)
        store.add_proof({"tranche_id": tid, "kind": kind, "file": name, "sha256": facts["sha256"],
                         "phash": facts["phash"], "meta": {k: facts.get(k) for k in
                                                           ("taken", "make", "model", "software", "gps", "size", "c2pa")},
                         "reading": v["receipt"] if kind == "receipt" else v["photo"]})
        files[kind] = name
    v["files"] = files
    v["via"] = via
    passed = sum(1 for x in v["checks"] if x["ok"])
    total = sum(1 for x in v["checks"] if x["ok"] is not None)
    store.log(c["id"], "proof", f"Proof for «{t['title']}» submitted via {via}: {passed}/{total} checks passed",
              None, tid, files["photo"])

    if v["decision"] == "approve":
        store.set_tranche(tid, status="verified", verdict=v)
        store.log(c["id"], "verdict", f"✅ AI approved «{t['title']}»: {v['summary']}", None, tid, files["photo"])
        paid = await _pay_verified(c["id"])
        v["paid"] = tid in paid
        if not v["paid"]:
            held = store.totals(c["id"])["held"]
            store.log(c["id"], "note", f"Waiting for funds: {money(held)} held, {money(t['amount'])} needed", None, tid)
    elif v["decision"] == "reject":
        store.set_tranche(tid, status="rejected", verdict=v)
        store.log(c["id"], "verdict", f"⛔ AI rejected the proof for «{t['title']}»: " + "; ".join(v["reasons"][:2]),
                  None, tid, files["photo"])
    else:
        store.set_tranche(tid, status="review", verdict=v)
        store.log(c["id"], "verdict", f"🔎 Proof for «{t['title']}» needs a human look: " + "; ".join(v["reasons"][:2]),
                  None, tid, files["photo"])
    if via != "telegram":
        await notify.send(c["volunteer_chat"], _volunteer_text(t, v))
    return v


def _volunteer_text(t: dict, v: dict) -> str:
    icon = {"approve": "✅", "reject": "⛔", "review": "🔎"}[v["decision"]]
    lines = [f"{icon} <b>{html.escape(t['title'])}</b> — {v['decision']}"]
    for c in v["checks"]:
        mark = {True: "✔", False: "✖", None: "·"}[c["ok"]]
        lines.append(f"{mark} {html.escape(c['name'])}: {html.escape(c['detail'][:120])}")
    lines += ["", html.escape(v["message_to_volunteer"])]
    if v.get("paid"):
        lines.append(f"\n💸 Sent {money(t['amount'])} to your PayPal.")
    return "\n".join(lines)


# ---------- payouts ----------

async def _pay_verified(cid: str) -> list[str]:
    """Pays every verified tranche the held money can cover, in order. Returns the paid tranche ids."""
    c = store.campaign(cid)
    paid = []
    for t in store.tranches(cid):
        if t["status"] != "verified":
            continue
        if store.totals(cid)["held"] + 1e-9 < t["amount"]:
            break
        try:
            r = await paypal.payout(c["volunteer_email"], t["amount"], c["currency"],
                                    f"Proof of Good: {t['title']}",
                                    f"Donors' money for «{t['title']}» ({c['title']}). Released after AI verification.")
        except PayPalError as ex:
            log.error("payout failed: %s", ex)
            store.log(cid, "note", f"Payout for «{t['title']}» failed: {html.escape(str(ex)[:120])}", None, t["id"])
            continue
        store.add_payout(r["batch_id"], t["id"], c["volunteer_email"], t["amount"], c["currency"], r["status"])
        store.set_tranche(t["id"], status="paid", paid_batch=r["batch_id"], paid_at=time.time())
        store.log(cid, "payout", f"💸 {money(t['amount'])} released to {c['volunteer_name']} for «{t['title']}»"
                                 f" (PayPal payout {r['batch_id']})", t["amount"], r["batch_id"])
        paid.append(t["id"])
        verdict = store.tranche(t["id"])["verdict"]
        summary = ""
        if verdict:
            import json
            summary = json.loads(verdict).get("summary", "")
        photo = next((p["file"] for p in store.proofs(t["id"]) if p["kind"] == "photo"), None)
        for chat in store.followers(cid):
            await notify.send(chat, f"✅ <b>{html.escape(c['title'])}</b>\n{html.escape(summary)}\n"
                                    f"{money(t['amount'])} released to the volunteer after AI verification.", photo)
        await notify.send(c["volunteer_chat"], f"💸 <b>{money(t['amount'])}</b> sent to your PayPal for "
                                               f"«{html.escape(t['title'])}».")
    if paid and all(t["status"] == "paid" for t in store.tranches(cid)):
        store.set_campaign(cid, status="completed")
        store.log(cid, "note", "🎉 Campaign completed — every tranche verified and paid")
    return paid


async def refresh_payouts() -> None:
    """Updates payout statuses from PayPal (UNCLAIMED -> SUCCESS when the volunteer has a PayPal account)."""
    for p in store._rows("SELECT * FROM payouts WHERE status NOT IN ('SUCCESS','FAILED','RETURNED')"):
        try:
            s = await paypal.payout_status(p["batch_id"])
            store.set_payout(p["batch_id"], status=s["item"] or s["batch"], transaction_id=s["transaction_id"])
        except PayPalError:
            pass


# ---------- refunds ----------

async def refund_campaign(cid: str, reason: str) -> dict:
    """The volunteer vanished or the deadline passed: every held donation goes back to its donor."""
    c = store.campaign(cid)
    done, failed = [], []
    for d in store.donations(cid):
        if d["status"] != "held":
            continue
        try:
            r = await paypal.refund(d["id"], d["amount"], d["currency"],
                                    f"Proof of Good refund: {c['title']} — {reason}")
            store.set_donation(d["id"], status="refunded", refund_id=r.get("id"))
            store.log(cid, "refund", f"↩️ {money(d['amount'])} refunded to {d['donor_name'] or 'donor'} — {reason}",
                      d["amount"], r.get("id"))
            done.append(d["id"])
        except PayPalError as ex:
            log.error("refund failed: %s", ex)
            failed.append(d["id"])
    store.set_campaign(cid, status="refunded")
    for chat in store.followers(cid):
        await notify.send(chat, f"↩️ <b>{html.escape(c['title'])}</b>: no verified proof — {html.escape(reason)}. "
                                f"Donations were refunded to donors' PayPal accounts.")
    return {"refunded": done, "failed": failed}
