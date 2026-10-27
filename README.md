# Proof of Good

**Donations that reach the volunteer one tranche at a time, on a transparent card — every payment checked by an AI
auditor, the next tranche released only after the last one is spent on the purpose and proven.**

Every disaster brings fake fundraisers, and small honest volunteers lose donors' trust. With an ordinary bank "jar" a
volunteer can take everything and vanish. With Proof of Good they never hold more than one tranche, every payment
from their campaign card is public and checked the moment it happens, and if the money is misused the rest goes back
to the donors automatically.

Built for the **PayPal AI Hackathon 2026** (PayPal sandbox + Gemini).

**Live demo: https://proof-of-good.onrender.com** · Telegram: [@paidup_agent2_bot](https://t.me/paidup_agent2_bot)
(free hosting — the first visit after a quiet period can take up to a minute to wake the server)

## How the money moves

| Step | What happens | PayPal |
|---|---|---|
| 1. Give | A donor pays with PayPal or any bank card. The money is captured to the platform account and **held**. | **Orders v2** |
| 2. One tranche to the card | When the next budget line is funded, it goes to the volunteer — and only that line. The volunteer needs no money of their own to start. | **Payouts v1** |
| 3. Every payment checked | The volunteer pays only with a dedicated campaign card. The bank reports each payment (merchant, category code, amount, fiscal receipt number). The AI auditor matches it to the purpose: **matched** / **unclear** (a receipt is asked for — e.g. cash on delivery at Nova Poshta) / **flagged** (cash withdrawal, card-to-card transfer, gambling, a night out → the campaign **freezes**). | — |
| 4. Prove | The volunteer sends a photo of what was bought, where it is used (and the receipt for unclear payments). Gemini checks the photo shows the item, is a real on-site photo, matches the purchase; code checks reuse (perceptual hash), capture date, editing software, C2PA credentials of AI generators. | — |
| 5. Next tranche or refund | Spent and proven → the tranche is "accounted for", donors get the photo, the next tranche is released. Frozen or vanished → every donor gets back their share of what is still held. | **Refunds v2** |

Each donor gets a page (`/d/<capture id>`) that shows exactly where their dollars are: held, on the card, spent and
proven, or refunded. Everything lands in a public ledger (AG Grid) with the real PayPal and bank ids.

## The transparent card

- **Real mode — Monobank** (Ukraine's largest online bank): the volunteer links a dedicated card with a **read-only**
  personal token from api.monobank.ua — it can read transactions, it cannot move money. Proof of Good registers a
  webhook (`POST /personal/webhook`) and the bank pushes every card transaction to `/hooks/mono/<secret>` as it happens.
  The same adapter pattern fits Plaid in the US, Open Banking in Europe.
- **Demo mode** (what the public demo uses — nobody's real bank statement is published): a simulated bank feed with
  the same transaction shape. The volunteer portal has buttons for honest and dishonest payments, so judges can try
  every case. Simulated payments are labelled "demo feed".

PayPal → Monobank: a volunteer withdraws the released tranche from PayPal to the campaign card (available for personal
accounts in Ukraine today).

## Try it (judges) — about 2 minutes

1. Open **[Try it yourself](https://proof-of-good.onrender.com/c/try)** and donate $10 with the PayPal button.
   Log in with the sandbox buyer shown on the page. The first tranche ($10) goes to the volunteer's demo card at once.
2. Open the **volunteer portal** with the code `TRY-IT`.
   - Press **"Pay … at Супермаркет"** — the auditor matches the payment to "bottled water". **"Cash on delivery at
     Nova Poshta"** comes back as *needs a receipt*.
   - Send a **photo of any bottle of water** near you (an original phone photo). The tranche is accounted for and the
     next one is released as soon as it is funded.
   - Try **"Fake: shop screenshots"** — rejected, with the reasons.
   - Cheat: **"Withdraw cash at an ATM"** or **"Send to another card"** — the campaign freezes on the spot.
   - **"Refund the held money"** — PayPal refunds every donor's held share. **"Reset the test campaign"** starts over.
3. Watch it all on the public page, the donor page and the **[Ledger](https://proof-of-good.onrender.com/ledger)**.

In Telegram the volunteer sends `/code TRY-IT`, then the photo (and receipt) — the audit runs step by step in the chat.
Donors `/follow try` to get a message when money is released and the photo when it is proven.

## Run it yourself

```bash
pip install -r requirements.txt
mkdir .secrets   # or use environment variables with the same names
echo YOUR_SANDBOX_CLIENT_ID     > .secrets/paypal_client_id.txt
echo YOUR_SANDBOX_CLIENT_SECRET > .secrets/paypal_client_secret.txt
echo YOUR_GEMINI_API_KEY        > .secrets/gemini_key.txt
echo YOUR_TELEGRAM_BOT_TOKEN    > .secrets/telegram_bot_token.txt   # optional, RUN_BOT=0 to skip
python run_web.py                # http://localhost:8000
```

Environment variables: `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET`, `GEMINI_API_KEY`, `TELEGRAM_BOT_TOKEN`,
`BOT_USERNAME`, `SANDBOX_BUYER` (test login shown to judges), `ADMIN_KEY` (enables `POST /api/demo/reset`),
`PUBLIC_URL` (for the bank webhook), `POG_DATA` (data folder), `RUN_BOT` (`0` = website only),
`ALLOW_MONOBANK` (`1` = let volunteers link a real Monobank card), `SPEND_MIN` (share of a tranche that must be spent
in matched payments, default 0.85).

## Code map

```
pog/service.py  money flow: donation → hold → release one tranche → card payments → evidence → next tranche / freeze / refund
pog/cards.py    the transparent card: merchant categories, red flags, AI matching, Monobank adapter, demo bank feed
pog/audit.py    the AI auditor of a tranche's evidence: bank feed + photo (+ receipt), file forensics, Gemini verdict
pog/paypal.py   PayPal REST client (Orders, Payouts, Refunds)
pog/web.py      FastAPI: pages, JSON API, live audit jobs, the bank webhook
pog/bot.py      Telegram bot for volunteers and donors
pog/store.py    SQLite: campaigns, tranches, donations, card payments, proofs, payouts, ledger
static/         the site (vanilla JS, PayPal JS SDK, AG Grid)
```

## AI tools used

- **Gemini 3.5 Flash** (Google AI API), structured JSON output with schemas:
  - matches each card payment to the purpose of the tranche (merchant + category + amount);
  - looks at the delivery photo (is the item there, is it a real on-site photo, which brand/model);
  - reads receipts for unclear payments;
  - weighs all the evidence, writes the verdict, the message to the volunteer and the update for donors.
- Deterministic checks a language model should not be trusted with alone: red-flag merchant categories, perceptual
  hashing (`imagehash`), EXIF (`Pillow`), C2PA content credentials (`c2pa-python`), the National Bank of Ukraine
  exchange rate.

## What's real and what's a demo

- All PayPal calls are real sandbox calls; the ids in the ledger can be looked up in the sandbox dashboard.
- The public demo's card is a simulated bank feed (no real person's transactions are published); the Monobank adapter
  is real code, enabled with `ALLOW_MONOBANK=1`.
- Production would add: PayPal Multiparty with delayed disbursement instead of platform-held funds, identity checks
  of volunteers, trust limits that grow with a volunteer's verified history, and a human review queue for the
  auditor's "review" verdicts.

MIT license.
