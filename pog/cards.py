"""The transparent card: every payment from the volunteer's campaign card is read from the bank and checked.

Real mode reads a Monobank card through Monobank's open API with a READ-ONLY personal token (it can see
transactions, it cannot move money): /personal/client-info lists the cards, /personal/webhook makes the bank POST
each new transaction to us as {type: "StatementItem", data: {account, statementItem}}.
Demo mode feeds the same handler with simulated transactions, so judges can try every case.
"""
import time
import uuid

import httpx

from . import audit

MONO_API = "https://api.monobank.ua"
CURRENCY = {980: "UAH", 840: "USD", 978: "EUR"}

MCC = {
    4111: "transport", 4121: "taxi", 4214: "freight and delivery", 4215: "courier and delivery service",
    4814: "telecom", 4829: "money transfer", 4900: "utilities", 5039: "construction materials",
    5045: "computers", 5065: "electrical parts", 5072: "hardware", 5122: "medicines (wholesale)",
    5200: "home supply warehouse", 5211: "building materials", 5251: "hardware store", 5261: "garden supply",
    5310: "discount store", 5311: "department store", 5399: "general merchandise", 5411: "supermarket",
    5499: "food store", 5541: "fuel station", 5542: "fuel dispenser", 5651: "clothing", 5712: "furniture",
    5722: "household appliances", 5732: "electronics", 5812: "restaurant", 5813: "bar or nightclub",
    5814: "fast food", 5912: "pharmacy", 5921: "liquor store", 5944: "jewellery", 5995: "pet shop",
    5999: "miscellaneous retail", 6010: "cash withdrawal at a bank", 6011: "ATM cash withdrawal",
    6012: "money sent to a financial account", 6051: "crypto or quasi-cash", 6538: "card-to-card transfer",
    6540: "card-to-card transfer", 7011: "hotel", 7273: "dating service", 7538: "car service", 7832: "cinema",
    7994: "video games", 7995: "gambling or betting", 8062: "hospital", 8099: "medical services", 8398: "charity",
}
# Money that leaves the purpose of a campaign however the volunteer explains it: frozen at once.
RED_FLAGS = {
    6010: "cash withdrawal", 6011: "cash withdrawal", 6012: "money moved to another account",
    6051: "crypto or quasi-cash", 6538: "transfer to another card", 6540: "transfer to another card",
    4829: "transfer to another person", 7995: "gambling", 7273: "dating service", 5813: "bar or nightclub",
    5921: "liquor store", 5944: "jewellery",
}

TX_SCHEMA = {"type": "OBJECT", "properties": {
    "fit": {"type": "STRING", "enum": ["yes", "unclear", "no"]},
    "reason": {"type": "STRING"},
}, "required": ["fit", "reason"]}


async def classify(tx: dict, tranche: dict | None, campaign: dict) -> tuple[str, str]:
    """(status, reason): matched | unclear | flagged."""
    mcc = tx.get("mcc")
    if mcc in RED_FLAGS:
        return "flagged", f"{RED_FLAGS[mcc]} — money left the campaign card instead of buying something"
    if not tranche:
        return "flagged", "a payment while no tranche was released for spending"
    prompt = (
        f"A volunteer pays from a dedicated card that only holds donated money. Campaign: «{campaign['title']}» in "
        f"{campaign['place']}. The money on the card right now is for: «{tranche['title']}» "
        f"({tranche['amount']:.2f} {campaign['currency']}).\n"
        f"Payment: merchant «{tx['description']}», merchant category {mcc} ({MCC.get(mcc, 'unknown')}), "
        f"{abs(tx['amount']):,.2f} {tx['currency']} (≈ {tx['usd']:.2f} {campaign['currency']}).\n"
        "Is this plausibly the purchase of that item? fit=yes if this kind of merchant sells it and the amount fits; "
        "fit=unclear if it could be it but the bank line does not show what was bought (cash on delivery at a "
        "courier, a marketplace, a payment to an individual entrepreneur) — then a receipt will be asked for; "
        "fit=no if it is unrelated to the purpose (food out, clothes, entertainment, a car for oneself...). "
        "One short sentence of reason.")
    r = await audit._generate([{"text": prompt}], TX_SCHEMA)
    return {"yes": "matched", "unclear": "unclear", "no": "flagged"}[r["fit"]], r["reason"]


# ---------- Monobank (real, read-only) ----------

async def mono_client_info(token: str) -> dict:
    async with httpx.AsyncClient(timeout=20) as http:
        r = await http.get(f"{MONO_API}/personal/client-info", headers={"X-Token": token})
        r.raise_for_status()
        return r.json()


async def mono_set_webhook(token: str, url: str) -> None:
    async with httpx.AsyncClient(timeout=30) as http:
        r = await http.post(f"{MONO_API}/personal/webhook", headers={"X-Token": token}, json={"webHookUrl": url})
        r.raise_for_status()


def from_mono(item: dict) -> dict:
    """A Monobank StatementItem -> our transaction dict (amounts in the card currency, minor units -> units)."""
    return {"id": f"mono-{item['id']}", "at": float(item["time"]), "description": item.get("description", ""),
            "mcc": item.get("mcc"), "amount": item["amount"] / 100, "currency": CURRENCY.get(item.get("currencyCode"), "UAH"),
            "receipt_id": item.get("receiptId"), "counter_name": item.get("counterName"), "raw": item}


# ---------- demo bank feed ----------

# (words in a tranche title) -> a shop that sells it, for the demo feed
_SHOPS = [
    (("water", "snack", "food", "cups", "napkin", "bread"), "Супермаркет «Колосок»", 5411),
    (("dog", "cat", "pet", "paws"), "Зоомагазин «Хвостик»", 5995),
    (("vet", "vaccin", "medic", "drug"), "Ветклініка «Айболить»", 8099),
    (("fuel", "petrol", "diesel"), "АЗС «Октан»", 5541),
    (("heater", "mat", "blanket"), "Електро-маркет «Ватт»", 5722),
    (("delivery", "installation"), "ФОП Коваль — монтаж", 7299),
]


def _shop_for(title: str) -> tuple[str, int]:
    low = title.lower()
    for words, name, mcc in _SHOPS:
        if any(w in low for w in words):
            return name, mcc
    return "Будмаркет — інструменти і техніка", 5200


def demo_presets(tranche: dict | None, rate: float) -> list[dict]:
    """Typical card payments for the tranche on the card, in hryvnias at today's rate (a card cannot pay more than
    the tranche put on it, so the «cheating» payments are scaled to it too)."""
    if not tranche:
        return []
    on_card = tranche["amount"] * rate
    uah = max(50, round(on_card * 0.97 / 10) * 10)
    part = lambda share, cap: max(50, min(cap, round(on_card * share / 10) * 10))
    shop, mcc = _shop_for(tranche["title"])
    atm, p2p, food = part(0.5, 5000), part(0.8, 20000), part(0.3, 1240)
    return [
        {"key": "store", "label": f"Pay ₴{uah:,.0f} at {shop}", "description": shop, "mcc": mcc, "amount": -uah},
        {"key": "np", "label": f"Pay ₴{uah:,.0f} cash on delivery at Nova Poshta", "description": "Нова Пошта",
         "mcc": 4215, "amount": -uah},
        {"key": "atm", "label": f"Withdraw ₴{atm:,.0f} cash at an ATM", "description": "Банкомат", "mcc": 6011,
         "amount": -atm},
        {"key": "p2p", "label": f"Send ₴{p2p:,.0f} to another card", "description": "Переказ на картку **** 7781",
         "mcc": 4829, "amount": -p2p},
        {"key": "food", "label": f"Pay ₴{food:,.0f} in a restaurant", "description": "Ресторан «Велика Ложка»",
         "mcc": 5812, "amount": -food},
    ]


def demo_tx(preset: dict) -> dict:
    return {"id": f"demo-{uuid.uuid4().hex[:10]}", "at": time.time(), "description": preset["description"],
            "mcc": preset["mcc"], "amount": float(preset["amount"]), "currency": "UAH",
            "receipt_id": f"DEMO-{uuid.uuid4().hex[:4].upper()}-{uuid.uuid4().hex[:4].upper()}"
            if preset["mcc"] not in RED_FLAGS else None, "simulated": 1, "raw": {"demo": preset.get("key")}}
