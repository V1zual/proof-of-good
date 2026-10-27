"""SQLite storage: campaigns and their budget (tranches), donations, the transparent card's payments, proofs,
payouts, refunds and the public ledger."""
import json
import sqlite3
import time
import uuid

from . import config

_SCHEMA = """
CREATE TABLE IF NOT EXISTS campaigns (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    story TEXT NOT NULL,
    place TEXT NOT NULL,            -- "Kyiv, Ukraine"
    country TEXT NOT NULL,
    volunteer_name TEXT NOT NULL,
    volunteer_email TEXT NOT NULL,  -- PayPal account that receives released tranches
    volunteer_chat INTEGER,         -- Telegram chat of the volunteer (set when they link the bot)
    volunteer_code TEXT NOT NULL,   -- secret code for the volunteer portal and the bot
    currency TEXT NOT NULL DEFAULT 'USD',
    status TEXT NOT NULL DEFAULT 'active',  -- active | frozen | completed | refunded
    frozen_reason TEXT,
    card_mode TEXT NOT NULL DEFAULT 'demo', -- demo (simulated bank feed) | monobank (real, read-only token)
    card_label TEXT,                -- "Monobank •• 4821"
    mono_token TEXT,                -- read-only Monobank personal token (real mode only)
    mono_account TEXT,
    hook_secret TEXT,               -- part of the bank webhook URL
    try_it INTEGER NOT NULL DEFAULT 0,      -- the public test campaign anyone may reset
    created REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS tranches (
    id TEXT PRIMARY KEY,
    campaign_id TEXT NOT NULL,
    position INTEGER NOT NULL,
    title TEXT NOT NULL,            -- "Petrol generator Hyundai HHY 3050F"
    amount REAL NOT NULL,           -- in the campaign currency
    status TEXT NOT NULL DEFAULT 'waiting',  -- waiting | released | accounted
    release_batch TEXT,             -- PayPal payout that sent it to the volunteer
    released_at REAL,
    photo_ok INTEGER NOT NULL DEFAULT 0,
    verdict TEXT,                   -- JSON of the last AI audit of the evidence
    accounted_at REAL
);
CREATE TABLE IF NOT EXISTS donations (
    id TEXT PRIMARY KEY,            -- PayPal capture id
    campaign_id TEXT NOT NULL,
    order_id TEXT NOT NULL,
    donor_name TEXT,
    donor_email TEXT,
    amount REAL NOT NULL,
    currency TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'held',  -- held | refunded (fully)
    refunded REAL NOT NULL DEFAULT 0,     -- part of it sent back to the donor
    refund_id TEXT,
    created REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS card_tx (
    id TEXT PRIMARY KEY,            -- bank transaction id
    campaign_id TEXT NOT NULL,
    tranche_id TEXT,                -- the tranche that was on the card when it was paid
    at REAL NOT NULL,
    description TEXT NOT NULL,      -- merchant as the bank shows it
    mcc INTEGER,
    amount REAL NOT NULL,           -- card currency, negative = spent
    currency TEXT NOT NULL,
    usd REAL,                       -- converted to the campaign currency (positive)
    receipt_id TEXT,                -- fiscal receipt number from the bank (check.gov.ua)
    counter_name TEXT,              -- who got the money on a transfer
    status TEXT NOT NULL,           -- matched | unclear | flagged | income
    reason TEXT,
    simulated INTEGER NOT NULL DEFAULT 0,
    raw TEXT
);
CREATE TABLE IF NOT EXISTS proofs (
    id TEXT PRIMARY KEY,
    tranche_id TEXT NOT NULL,
    kind TEXT NOT NULL,             -- photo | receipt
    file TEXT NOT NULL,             -- file name inside UPLOAD_DIR
    sha256 TEXT NOT NULL,
    phash TEXT,
    meta TEXT,                      -- JSON: exif, c2pa, size
    reading TEXT,                   -- JSON: what the AI read in it
    created REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS payouts (
    batch_id TEXT PRIMARY KEY,
    tranche_id TEXT NOT NULL,
    email TEXT NOT NULL,
    amount REAL NOT NULL,
    currency TEXT NOT NULL,
    status TEXT,
    transaction_id TEXT,
    created REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS followers (
    campaign_id TEXT NOT NULL,
    chat_id INTEGER NOT NULL,
    PRIMARY KEY (campaign_id, chat_id)
);
CREATE TABLE IF NOT EXISTS ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id TEXT NOT NULL,
    at REAL NOT NULL,
    kind TEXT NOT NULL,             -- donation | release | card | flag | proof | verdict | refund | note
    amount REAL,
    text TEXT NOT NULL,
    ref TEXT,                       -- PayPal id, bank transaction id or tranche id
    photo TEXT                      -- proof file to show next to the entry
);
"""
_TABLES = ("campaigns", "tranches", "donations", "card_tx", "proofs", "payouts", "followers", "ledger")


def _db() -> sqlite3.Connection:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(config.DB_PATH)
    con.row_factory = sqlite3.Row
    con.executescript(_SCHEMA)
    return con


def _rows(sql: str, *args) -> list[dict]:
    with _db() as con:
        return [dict(r) for r in con.execute(sql, args)]


def _row(sql: str, *args) -> dict | None:
    rows = _rows(sql, *args)
    return rows[0] if rows else None


def _exec(sql: str, *args) -> None:
    with _db() as con:
        con.execute(sql, args)


def _update(table: str, key: str, value, fields: dict) -> None:
    cols = ", ".join(f"{k}=?" for k in fields)
    _exec(f"UPDATE {table} SET {cols} WHERE {key}=?", *fields.values(), value)


# --- campaigns ---

def add_campaign(c: dict, tranches: list[dict]) -> str:
    cid = c.get("id") or uuid.uuid4().hex[:8]
    with _db() as con:
        con.execute(
            "INSERT OR REPLACE INTO campaigns (id, title, story, place, country, volunteer_name, volunteer_email,"
            " volunteer_code, currency, status, card_mode, card_label, hook_secret, try_it, created)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (cid, c["title"], c["story"], c["place"], c["country"], c["volunteer_name"], c["volunteer_email"],
             c.get("volunteer_code") or uuid.uuid4().hex[:6].upper(), c.get("currency", "USD"), "active",
             c.get("card_mode", "demo"), c.get("card_label") or "Demo card •• 0000", uuid.uuid4().hex,
             int(c.get("try_it", 0)), time.time()))
        con.execute("DELETE FROM tranches WHERE campaign_id=?", (cid,))
        for i, t in enumerate(tranches):
            con.execute("INSERT INTO tranches (id, campaign_id, position, title, amount) VALUES (?,?,?,?,?)",
                        (t.get("id") or uuid.uuid4().hex[:8], cid, i, t["title"], float(t["amount"])))
    return cid


def campaigns() -> list[dict]:
    return _rows("SELECT * FROM campaigns ORDER BY try_it, created")


def campaign(cid: str) -> dict | None:
    return _row("SELECT * FROM campaigns WHERE id=?", cid)


def campaign_by_code(code: str) -> dict | None:
    return _row("SELECT * FROM campaigns WHERE volunteer_code=?", code.strip().upper())


def campaign_by_hook(secret: str) -> dict | None:
    return _row("SELECT * FROM campaigns WHERE hook_secret=?", secret)


def set_campaign(cid: str, **fields) -> None:
    _update("campaigns", "id", cid, fields)


def delete_campaign_data(cid: str) -> None:
    """Forgets everything that happened in a campaign (used to reset the public test campaign)."""
    with _db() as con:
        tids = [r[0] for r in con.execute("SELECT id FROM tranches WHERE campaign_id=?", (cid,))]
        for tid in tids:
            con.execute("DELETE FROM proofs WHERE tranche_id=?", (tid,))
            con.execute("DELETE FROM payouts WHERE tranche_id=?", (tid,))
        for t in ("donations", "card_tx", "ledger"):
            con.execute(f"DELETE FROM {t} WHERE campaign_id=?", (cid,))
        con.execute("UPDATE tranches SET status='waiting', release_batch=NULL, released_at=NULL, photo_ok=0,"
                    " verdict=NULL, accounted_at=NULL WHERE campaign_id=?", (cid,))
        con.execute("UPDATE campaigns SET status='active', frozen_reason=NULL WHERE id=?", (cid,))


# --- tranches ---

def tranches(cid: str) -> list[dict]:
    return _rows("SELECT * FROM tranches WHERE campaign_id=? ORDER BY position", cid)


def tranche(tid: str) -> dict | None:
    return _row("SELECT * FROM tranches WHERE id=?", tid)


def current_tranche(cid: str) -> dict | None:
    """The tranche that is on the volunteer's card right now (released, not yet accounted for)."""
    return _row("SELECT * FROM tranches WHERE campaign_id=? AND status='released' ORDER BY position LIMIT 1", cid)


def set_tranche(tid: str, **fields) -> None:
    if "verdict" in fields and fields["verdict"] is not None and not isinstance(fields["verdict"], str):
        fields["verdict"] = json.dumps(fields["verdict"], ensure_ascii=False)
    _update("tranches", "id", tid, fields)


# --- donations ---

def add_donation(d: dict) -> None:
    _exec("INSERT OR REPLACE INTO donations (id, campaign_id, order_id, donor_name, donor_email, amount, currency,"
          " status, created) VALUES (?,?,?,?,?,?,?,?,?)",
          d["id"], d["campaign_id"], d["order_id"], d.get("donor_name"), d.get("donor_email"), d["amount"],
          d["currency"], "held", time.time())


def donations(cid: str) -> list[dict]:
    return _rows("SELECT * FROM donations WHERE campaign_id=? ORDER BY created", cid)


def donation(did: str) -> dict | None:
    return _row("SELECT * FROM donations WHERE id=?", did)


def set_donation(did: str, **fields) -> None:
    _update("donations", "id", did, fields)


# --- the transparent card ---

def add_card_tx(tx: dict) -> bool:
    """Stores a bank transaction once; returns False if it was already there (webhooks may repeat)."""
    if _row("SELECT 1 x FROM card_tx WHERE id=?", tx["id"]):
        return False
    _exec("INSERT INTO card_tx (id, campaign_id, tranche_id, at, description, mcc, amount, currency, usd, receipt_id,"
          " counter_name, status, reason, simulated, raw) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
          tx["id"], tx["campaign_id"], tx.get("tranche_id"), tx["at"], tx["description"], tx.get("mcc"), tx["amount"],
          tx["currency"], tx.get("usd"), tx.get("receipt_id"), tx.get("counter_name"), tx["status"], tx.get("reason"),
          int(tx.get("simulated", 0)), json.dumps(tx.get("raw") or {}, ensure_ascii=False))
    return True


def card_txs(cid: str, tid: str | None = None) -> list[dict]:
    if tid:
        return _rows("SELECT * FROM card_tx WHERE campaign_id=? AND tranche_id=? ORDER BY at", cid, tid)
    return _rows("SELECT * FROM card_tx WHERE campaign_id=? ORDER BY at DESC", cid)


def set_card_tx(txid: str, **fields) -> None:
    _update("card_tx", "id", txid, fields)


def spent(tid: str) -> float:
    """What the card spent on a tranche in purchases the auditor matched to it (campaign currency)."""
    r = _row("SELECT COALESCE(SUM(usd),0) s FROM card_tx WHERE tranche_id=? AND status='matched'", tid)
    return round(r["s"], 2)


# --- totals ---

def totals(cid: str) -> dict:
    """raised: donations kept · released: sent to the volunteer's card · spent: card purchases matched by the
    auditor · held: still on the PayPal account · accounted: tranches with matched spending and a verified photo."""
    one = lambda sql: _row(sql, cid)["s"]
    raised = one("SELECT COALESCE(SUM(amount - refunded),0) s FROM donations WHERE campaign_id=?")
    refunded = one("SELECT COALESCE(SUM(refunded),0) s FROM donations WHERE campaign_id=?")
    released = one("SELECT COALESCE(SUM(amount),0) s FROM tranches WHERE campaign_id=? AND status IN ('released','accounted')")
    accounted = one("SELECT COALESCE(SUM(amount),0) s FROM tranches WHERE campaign_id=? AND status='accounted'")
    goal = one("SELECT COALESCE(SUM(amount),0) s FROM tranches WHERE campaign_id=?")
    spent_ = one("SELECT COALESCE(SUM(usd),0) s FROM card_tx WHERE campaign_id=? AND status='matched'")
    flagged = one("SELECT COALESCE(SUM(usd),0) s FROM card_tx WHERE campaign_id=? AND status='flagged'")
    donors = _row("SELECT COUNT(*) s FROM donations WHERE campaign_id=? AND status!='refunded'", cid)["s"]
    r2 = lambda x: round(x, 2)
    return {"raised": r2(raised), "released": r2(released), "accounted": r2(accounted), "spent": r2(spent_),
            "flagged": r2(flagged), "held": r2(max(0.0, raised - released)), "goal": r2(goal),
            "refunded": r2(refunded), "donors": donors}


# --- proofs ---

def add_proof(p: dict) -> str:
    pid = uuid.uuid4().hex[:10]
    _exec("INSERT INTO proofs (id, tranche_id, kind, file, sha256, phash, meta, reading, created)"
          " VALUES (?,?,?,?,?,?,?,?,?)",
          pid, p["tranche_id"], p["kind"], p["file"], p["sha256"], p.get("phash"),
          json.dumps(p.get("meta") or {}, ensure_ascii=False), json.dumps(p.get("reading") or {}, ensure_ascii=False),
          time.time())
    return pid


def proofs(tid: str) -> list[dict]:
    return _rows("SELECT * FROM proofs WHERE tranche_id=? ORDER BY created", tid)


def all_phashes(exclude_tranche: str | None = None) -> list[tuple[str, str, str]]:
    """(phash, proof id, tranche id) of every stored photo — to catch a picture used twice."""
    rows = _rows("SELECT phash, id, tranche_id FROM proofs WHERE phash IS NOT NULL")
    return [(r["phash"], r["id"], r["tranche_id"]) for r in rows if r["tranche_id"] != exclude_tranche]


def all_shas(exclude_tranche: str | None = None) -> set[str]:
    rows = _rows("SELECT sha256, tranche_id FROM proofs")
    return {r["sha256"] for r in rows if r["tranche_id"] != exclude_tranche}


# --- followers (donors who want updates in Telegram) ---

def follow(cid: str, chat_id: int) -> None:
    _exec("INSERT OR IGNORE INTO followers (campaign_id, chat_id) VALUES (?,?)", cid, chat_id)


def followers(cid: str) -> list[int]:
    return [r["chat_id"] for r in _rows("SELECT chat_id FROM followers WHERE campaign_id=?", cid)]


# --- payouts, ledger ---

def add_payout(batch_id: str, tid: str, email: str, amount: float, currency: str, status: str) -> None:
    _exec("INSERT INTO payouts (batch_id, tranche_id, email, amount, currency, status, created) VALUES (?,?,?,?,?,?,?)",
          batch_id, tid, email, amount, currency, status, time.time())


def open_payouts() -> list[dict]:
    return _rows("SELECT * FROM payouts WHERE COALESCE(status,'') NOT IN ('SUCCESS','FAILED','RETURNED','BLOCKED')")


def set_payout(batch_id: str, **fields) -> None:
    _update("payouts", "batch_id", batch_id, fields)


def log(cid: str, kind: str, text: str, amount: float | None = None, ref: str | None = None,
        photo: str | None = None) -> None:
    _exec("INSERT INTO ledger (campaign_id, at, kind, amount, text, ref, photo) VALUES (?,?,?,?,?,?,?)",
          cid, time.time(), kind, amount, text, ref, photo)


def ledger(cid: str | None = None) -> list[dict]:
    if cid:
        return _rows("SELECT * FROM ledger WHERE campaign_id=? ORDER BY at DESC, id DESC", cid)
    return _rows("SELECT * FROM ledger ORDER BY at DESC, id DESC")


def reset() -> None:
    """Wipes everything (demo re-seed)."""
    with _db() as con:
        for t in _TABLES:
            con.execute(f"DROP TABLE IF EXISTS {t}")
        con.executescript(_SCHEMA)
