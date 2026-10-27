"""The money flow, shared by the website and the Telegram bot.

  donation      PayPal Orders: captured to the platform account and held
  release       one tranche at a time goes to the volunteer (PayPal Payouts) for their transparent card
  card payment  every payment from that card comes from the bank and is checked at once:
                matched / unclear (a receipt is asked for) / flagged (cash, transfers... — the campaign freezes)
  evidence      a photo of the item delivered (+ receipt for unclear payments) is audited; when the tranche is
                spent and proven it is «accounted» and the next tranche is released
  refund        held money goes back to the donors (PayPal Refunds), each one's share
"""
import html
import json
import logging
import time

from . import audit, cards, config, notify, store
from .paypal import PayPal, PayPalError

log = logging.getLogger("pog.service")
paypal = PayPal()


def money(amount: float, currency: str = "USD") -> str:
    return f"${amount:,.2f}" if currency == "USD" else f"{amount:,.2f} {currency}"


def uah(amount: float) -> str:
    return f"₴{abs(amount):,.0f}"


# ---------- donations ----------

async def start_donation(cid: str, amount: float) -> str:
    c = store.campaign(cid)
    if not c or c["status"] != "active":
        raise ValueError("this campaign is not accepting donations")
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
    store.log(cid, "donation", f"{who} donated {money(cap['amount'], cap['currency'])} — held on PayPal",
              cap["amount"], cap["capture_id"])
    totals = store.totals(cid)
    await notify.send(c["volunteer_chat"],
                      f"💙 {html.escape(who)} donated <b>{money(cap['amount'])}</b> to «{html.escape(c['title'])}». "
                      f"Raised {money(totals['raised'])} of {money(totals['goal'])}.")
    await release_next(cid)
    return {"donation": cap, "totals": store.totals(cid)}


# ---------- releases ----------

async def release_next(cid: str, on_step: audit.Step = None) -> dict | None:
    """Sends the next tranche to the volunteer when the previous one is accounted for and enough money is held."""
    c = store.campaign(cid)
    if not c or c["status"] != "active" or store.current_tranche(cid):
        return None
    nxt = next((t for t in store.tranches(cid) if t["status"] == "waiting"), None)
    if not nxt or store.totals(cid)["held"] + 1e-9 < nxt["amount"]:
        return None
    if on_step:
        await on_step({"kind": "stage", "name": f"Releasing the next tranche: {money(nxt['amount'])}"})
    try:
        r = await paypal.payout(c["volunteer_email"], nxt["amount"], c["currency"], f"Proof of Good: {nxt['title']}",
                                f"Donors' money for «{nxt['title']}» ({c['title']}). Move it to your campaign card "
                                f"and pay with that card — every payment is checked.")
    except PayPalError as ex:
        log.error("release failed: %s", ex)
        store.log(cid, "note", f"Release of «{nxt['title']}» failed: {str(ex)[:120]}", None, nxt["id"])
        return None
    store.add_payout(r["batch_id"], nxt["id"], c["volunteer_email"], nxt["amount"], c["currency"], r["status"])
    store.set_tranche(nxt["id"], status="released", release_batch=r["batch_id"], released_at=time.time())
    store.log(cid, "release", f"💸 {money(nxt['amount'])} released to {c['volunteer_name']}'s transparent card for "
                              f"«{nxt['title']}» — every payment from the card is now checked", nxt["amount"], r["batch_id"])
    if on_step:
        await on_step({"kind": "release", "amount": nxt["amount"], "batch": r["batch_id"], "tranche": nxt["title"],
                       "to": c["volunteer_name"]})
    await notify.send(c["volunteer_chat"], f"💸 <b>{money(nxt['amount'])}</b> for «{html.escape(nxt['title'])}» is on "
                                           f"its way to your PayPal. Move it to your campaign card, pay with that card, "
                                           f"then send me a photo of the item in place.")
    for chat in store.followers(cid):
        await notify.send(chat, f"💸 <b>{html.escape(c['title'])}</b>: {money(nxt['amount'])} released for "
                                f"«{html.escape(nxt['title'])}». Every card payment will show up on the page.")
    return nxt


# ---------- the transparent card ----------

async def card_payment(cid: str, tx: dict) -> dict | None:
    """A payment (or a top-up) from the volunteer's campaign card, from the bank webhook or the demo feed."""
    c = store.campaign(cid)
    if not c:
        return None
    tr = store.current_tranche(cid)
    tx["campaign_id"], tx["tranche_id"] = cid, tr["id"] if tr else None
    try:
        tx["usd"] = await audit.convert(abs(tx["amount"]), tx["currency"], c["currency"])
    except Exception:
        tx["usd"] = None
    if tx["amount"] >= 0:  # money arriving on the card: the withdrawal from PayPal
        tx["status"], tx["reason"] = "income", "money moved onto the card"
        if store.add_card_tx(tx):
            store.log(cid, "card", f"💳 +{uah(tx['amount'])} arrived on the card ({tx['description']})", tx["usd"], tx["id"])
        return tx
    if c["status"] not in ("active", "frozen"):
        tx["status"], tx["reason"] = "flagged", f"a payment after the campaign was {c['status']}"
    else:
        tx["status"], tx["reason"] = await cards.classify(tx, tr, c)
    if not store.add_card_tx(tx):
        return None
    icon = {"matched": "✅", "unclear": "❔", "flagged": "⛔"}[tx["status"]]
    store.log(cid, "card", f"💳 −{uah(tx['amount'])} at {tx['description']} ({money(tx['usd'] or 0)}) {icon} "
                           f"{tx['reason']}", tx["usd"], tx["id"])
    if tx["status"] == "flagged":
        await freeze(cid, f"−{uah(tx['amount'])} at {tx['description']}: {tx['reason']}")
    elif tx["status"] == "unclear":
        await notify.send(c["volunteer_chat"], f"❔ −{uah(tx['amount'])} at {html.escape(tx['description'])}: the bank "
                                               f"line doesn't say what was bought. Send the receipt with the photo.")
    return tx


async def freeze(cid: str, reason: str) -> None:
    c = store.campaign(cid)
    if c["status"] == "frozen":
        return
    store.set_campaign(cid, status="frozen", frozen_reason=reason)
    store.log(cid, "flag", f"⛔ Spending frozen — {reason}. No more money is released; held donations go back to "
                           f"donors if this is not explained.")
    await notify.send(c["volunteer_chat"], f"⛔ <b>Your campaign card is frozen.</b>\n{html.escape(reason)}\n"
                                           f"No more money will be released.")
    for chat in store.followers(cid):
        await notify.send(chat, f"⛔ <b>{html.escape(c['title'])}</b>: spending frozen — {html.escape(reason)}.")


# ---------- evidence ----------

def check_tranche(tid: str) -> tuple[dict, dict]:
    t = store.tranche(tid)
    c = store.campaign(t["campaign_id"]) if t else None
    if not t or not c:
        raise ValueError("unknown tranche")
    if c["status"] != "active":
        raise ValueError(f"this campaign is {c['status']}")
    if t["status"] != "released":
        raise ValueError("this tranche is not on the card: evidence is sent for the tranche that was released")
    return t, c


async def submit_evidence(tid: str, photo: bytes, receipt: bytes | None, via: str,
                          on_step: audit.Step = None) -> dict:
    t, c = check_tranche(tid)
    v = await audit.audit_evidence(t, c, store.card_txs(c["id"], tid), photo, receipt,
                                   store.all_phashes(tid), store.all_shas(tid), on_step)
    files = {}
    config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    for kind, data, facts, reading in (("photo", photo, v["photo_facts"], v["photo"]),
                                       ("receipt", receipt, v["receipt_facts"], v["receipt"])):
        if not data:
            continue
        name = f"{tid}_{int(time.time())}_{kind}.jpg"
        (config.UPLOAD_DIR / name).write_bytes(data)
        store.add_proof({"tranche_id": tid, "kind": kind, "file": name, "sha256": facts["sha256"],
                         "phash": facts["phash"], "reading": reading,
                         "meta": {k: facts.get(k) for k in ("taken", "make", "model", "software", "gps", "size", "c2pa")}})
        files[kind] = name
    v["files"], v["via"] = files, via
    for txid in v["matched_tx"]:
        store.set_card_tx(txid, status="matched", reason="explained by the receipt")
    passed = sum(1 for x in v["checks"] if x["ok"])
    total = sum(1 for x in v["checks"] if x["ok"] is not None)
    store.log(c["id"], "proof", f"Evidence for «{t['title']}» sent via {via}: {passed}/{total} checks passed",
              None, tid, files.get("photo"))
    if v["accounted"]:
        store.set_tranche(tid, status="accounted", photo_ok=1, verdict=v, accounted_at=time.time())
        store.log(c["id"], "verdict", f"✅ «{t['title']}» accounted for: {v['summary']}", v["spent"], tid, files.get("photo"))
        for chat in store.followers(c["id"]):
            await notify.send(chat, f"✅ <b>{html.escape(c['title'])}</b>\n{html.escape(v['summary'])}", files.get("photo"))
        v["released"] = await release_next(c["id"], on_step)
        if all(x["status"] == "accounted" for x in store.tranches(c["id"])):
            store.set_campaign(c["id"], status="completed")
            store.log(c["id"], "note", "🎉 Campaign completed — every tranche spent and proven")
    else:
        store.set_tranche(tid, photo_ok=int(v["photo_ok"]), verdict=v)
        icon = "⛔" if v["decision"] == "reject" else "🔎"
        store.log(c["id"], "verdict", f"{icon} «{t['title']}» not accounted yet: " + "; ".join(v["reasons"][:2]),
                  None, tid, files.get("photo"))
    if via != "telegram":
        await notify.send(c["volunteer_chat"], volunteer_text(store.tranche(tid), v))
    return v


def volunteer_text(t: dict, v: dict) -> str:
    head = "✅ accounted" if v["accounted"] else {"approve": "🔎 almost", "reject": "⛔ rejected", "review": "🔎 not yet"}[v["decision"]]
    lines = [f"<b>{html.escape(t['title'])}</b> — {head}"]
    for c in v["checks"]:
        mark = {True: "✔", False: "✖", None: "·"}[c["ok"]]
        lines.append(f"{mark} {html.escape(c['name'])}: {html.escape(c['detail'][:110])}")
    lines += ["", html.escape(v["message_to_volunteer"])]
    if v.get("released"):
        lines.append(f"\n💸 Next tranche released: {money(v['released']['amount'])} for «{html.escape(v['released']['title'])}».")
    return "\n".join(lines)


async def refresh_payouts() -> None:
    """Updates payout statuses from PayPal (UNCLAIMED -> SUCCESS when the receiver has a PayPal account)."""
    for p in store.open_payouts():
        try:
            s = await paypal.payout_status(p["batch_id"])
            store.set_payout(p["batch_id"], status=s["item"] or s["batch"], transaction_id=s["transaction_id"])
        except PayPalError:
            pass


# ---------- where a donor's money is ----------

def allocation(cid: str) -> dict[str, list[dict]]:
    """Donations fill the tranches in order (first dollar in, first tranche). For each donation: the parts of it
    that went to each tranche, with that tranche's state — so a donor sees exactly what their money bought."""
    bounds, start = [], 0.0
    for t in store.tranches(cid):
        bounds.append((start, start + t["amount"], t))
        start += t["amount"]
    out, pos = {}, 0.0
    for d in store.donations(cid):
        parts = []
        lo, hi = pos, pos + d["amount"]
        for a, b, t in bounds:
            share = min(hi, b) - max(lo, a)
            if share > 0.004:
                parts.append({"amount": round(share, 2), "state": t["status"], "tranche": t["id"], "title": t["title"]})
        extra = hi - max(lo, start)
        if extra > 0.004:
            parts.append({"amount": round(min(extra, d["amount"]), 2), "state": "surplus"})
        pos = hi
        # money sent back came out of the parts that were still held
        back = d["refunded"]
        for p in parts:
            if back > 0.004 and p["state"] in ("waiting", "surplus"):
                p["state"] = "refunded"
                back -= p["amount"]
        out[d["id"]] = parts
    return out


# ---------- refunds ----------

async def refund_campaign(cid: str, reason: str) -> dict:
    """Sends every donor back their share of the money still held on PayPal and closes the campaign."""
    c = store.campaign(cid)
    alloc = allocation(cid)
    done, failed = [], []
    for d in store.donations(cid):
        if d["status"] == "refunded":
            continue
        held = round(sum(p["amount"] for p in alloc.get(d["id"], []) if p["state"] in ("waiting", "surplus")), 2)
        if held < 0.01:
            continue
        try:
            r = await paypal.refund(d["id"], held, d["currency"], f"Proof of Good refund: {c['title']} — {reason}")
            whole = held >= d["amount"] - 0.01
            store.set_donation(d["id"], status="refunded" if whole else "held", refund_id=r.get("id"),
                               refunded=round(d["refunded"] + held, 2))
            store.log(cid, "refund", f"↩️ {money(held)} refunded to {d['donor_name'] or 'a donor'} — {reason}",
                      held, r.get("id"))
            done.append(d["id"])
        except PayPalError as ex:
            log.error("refund failed: %s", ex)
            failed.append(d["id"])
    store.set_campaign(cid, status="refunded")
    for chat in store.followers(cid):
        await notify.send(chat, f"↩️ <b>{html.escape(c['title'])}</b>: {html.escape(reason)}. "
                                f"The money still held was refunded to donors' PayPal accounts.")
    return {"refunded": done, "failed": failed}


async def reset_try_campaign(cid: str) -> None:
    """The public test campaign: give the testers' sandbox money back and start it over."""
    c = store.campaign(cid)
    if not c or not c["try_it"]:
        raise ValueError("only the test campaign can be reset")
    if c["status"] in ("active", "frozen"):
        await refund_campaign(cid, "the test campaign was reset")
    store.delete_campaign_data(cid)
    store.log(cid, "note", "Test campaign reset — try the whole flow from the first donation")
