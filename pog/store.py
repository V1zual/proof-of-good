"""SQLite storage: campaigns, their tranches, donations, proofs, payouts, refunds and the public ledger."""
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
    country TEXT NOT NULL,          -- ISO code used for receipt currency and GPS checks
    volunteer_name TEXT NOT NULL,
    volunteer_email TEXT NOT NULL,  -- PayPal account that receives the tranches
    volunteer_chat INTEGER,         -- Telegram chat of the volunteer (set when they link the bot)
    volunteer_code TEXT NOT NULL,   -- secret code the volunteer types into the bot
    currency TEXT NOT NULL DEFAULT 'USD',
    status TEXT NOT NULL DEFAULT 'active',  -- active | completed | refunded
    created REAL NOT NULL,
    cover TEXT                      -- cover image file name (optional)
);
CREATE TABLE IF NOT EXISTS tranches (
    id TEXT PRIMARY KEY,
    campaign_id TEXT NOT NULL,
    position INTEGER NOT NULL,
    title TEXT NOT NULL,            -- "Generator Hyundai HHY 3050F"
    amount REAL NOT NULL,           -- in the campaign currency
    status TEXT NOT NULL DEFAULT 'waiting',  -- waiting | checking | verified | rejected | paid
    verdict TEXT,                   -- JSON of the last AI audit
    paid_batch TEXT,
    paid_at REAL
);
CREATE TABLE IF NOT EXISTS donations (
    id TEXT PRIMARY KEY,            -- PayPal capture id
    campaign_id TEXT NOT NULL,
    order_id TEXT NOT NULL,
    donor_name TEXT,
    donor_email TEXT,
    donor_chat INTEGER,             -- Telegram chat if the donor follows the campaign
    amount REAL NOT NULL,
    currency TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'held',  -- held | spent | refunded
    refund_id TEXT,
    created REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS proofs (
    id TEXT PRIMARY KEY,
    tranche_id TEXT NOT NULL,
    kind TEXT NOT NULL,             -- receipt | photo
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
    kind TEXT NOT NULL,             -- donation | proof | verdict | payout | refund | note
    amount REAL,
    text TEXT NOT NULL,
    ref TEXT,                       -- PayPal id or proof id
    photo TEXT                      -- proof file to show next to the entry
);
"""


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


# --- campaigns ---

def add_campaign(c: dict, tranches: list[dict]) -> str:
    cid = c.get("id") or uuid.uuid4().hex[:8]
    with _db() as con:
        con.execute(
            "INSERT OR REPLACE INTO campaigns (id, title, story, place, country, volunteer_name, volunteer_email,"
            " volunteer_code, currency, status, created, cover) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (cid, c["title"], c["story"], c["place"], c["country"], c["volunteer_name"], c["volunteer_email"],
             c.get("volunteer_code") or uuid.uuid4().hex[:6].upper(), c.get("currency", "USD"), "active",
             time.time(), c.get("cover")))
        con.execute("DELETE FROM tranches WHERE campaign_id=?", (cid,))
        for i, t in enumerate(tranches):
            con.execute("INSERT INTO tranches (id, campaign_id, position, title, amount) VALUES (?,?,?,?,?)",
                        (t.get("id") or uuid.uuid4().hex[:8], cid, i, t["title"], float(t["amount"])))
    return cid


def campaigns() -> list[dict]:
    return _rows("SELECT * FROM campaigns ORDER BY created")


def campaign(cid: str) -> dict | None:
    return _row("SELECT * FROM campaigns WHERE id=?", cid)


def campaign_by_code(code: str) -> dict | None:
    return _row("SELECT * FROM campaigns WHERE volunteer_code=?", code.strip().upper())


def set_campaign(cid: str, **fields) -> None:
    cols = ", ".join(f"{k}=?" for k in fields)
    _exec(f"UPDATE campaigns SET {cols} WHERE id=?", *fields.values(), cid)


# --- tranches ---

def tranches(cid: str) -> list[dict]:
    return _rows("SELECT * FROM tranches WHERE campaign_id=? ORDER BY position", cid)


def tranche(tid: str) -> dict | None:
    return _row("SELECT * FROM tranches WHERE id=?", tid)


def set_tranche(tid: str, **fields) -> None:
    if "verdict" in fields and not isinstance(fields["verdict"], str):
        fields["verdict"] = json.dumps(fields["verdict"], ensure_ascii=False)
    cols = ", ".join(f"{k}=?" for k in fields)
    _exec(f"UPDATE tranches SET {cols} WHERE id=?", *fields.values(), tid)


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
    cols = ", ".join(f"{k}=?" for k in fields)
    _exec(f"UPDATE donations SET {cols} WHERE id=?", *fields.values(), did)


def totals(cid: str) -> dict:
    """raised = all captured donations, paid = paid tranches, held = still on the platform account."""
    raised = _row("SELECT COALESCE(SUM(amount),0) s FROM donations WHERE campaign_id=? AND status!='refunded'", cid)["s"]
    paid = _row("SELECT COALESCE(SUM(amount),0) s FROM tranches WHERE campaign_id=? AND status='paid'", cid)["s"]
    goal = _row("SELECT COALESCE(SUM(amount),0) s FROM tranches WHERE campaign_id=?", cid)["s"]
    refunded = _row("SELECT COALESCE(SUM(amount),0) s FROM donations WHERE campaign_id=? AND status='refunded'", cid)["s"]
    donors = _row("SELECT COUNT(*) n FROM donations WHERE campaign_id=? AND status!='refunded'", cid)["n"]
    return {"raised": round(raised, 2), "paid": round(paid, 2), "held": round(raised - paid, 2),
            "goal": round(goal, 2), "refunded": round(refunded, 2), "donors": donors}


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


def all_proofs() -> list[dict]:
    return _rows("SELECT p.*, t.campaign_id FROM proofs p JOIN tranches t ON t.id=p.tranche_id ORDER BY p.created")


# --- followers (donors who want updates in Telegram) ---

def follow(cid: str, chat_id: int) -> None:
    _exec("INSERT OR IGNORE INTO followers (campaign_id, chat_id) VALUES (?,?)", cid, chat_id)


def followers(cid: str) -> list[int]:
    return [r["chat_id"] for r in _rows("SELECT chat_id FROM followers WHERE campaign_id=?", cid)]


# --- payouts, ledger ---

def add_payout(batch_id: str, tid: str, email: str, amount: float, currency: str, status: str) -> None:
    _exec("INSERT INTO payouts (batch_id, tranche_id, email, amount, currency, status, created) VALUES (?,?,?,?,?,?,?)",
          batch_id, tid, email, amount, currency, status, time.time())


def set_payout(batch_id: str, **fields) -> None:
    cols = ", ".join(f"{k}=?" for k in fields)
    _exec(f"UPDATE payouts SET {cols} WHERE batch_id=?", *fields.values(), batch_id)


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
        for t in ("campaigns", "tranches", "donations", "proofs", "payouts", "ledger", "followers"):
            con.execute(f"DELETE FROM {t}")
