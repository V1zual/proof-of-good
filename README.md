# Proof of Good

**Donations that are released only after an AI auditor verifies the proof.**

Every disaster brings fake fundraisers. People stop giving because they never learn where the money went.
Proof of Good holds donations on PayPal, lets the volunteer buy the thing, and releases the money tranche by
tranche — only after the receipt and a photo from the spot pass an AI audit. If no proof ever arrives,
every donor is refunded automatically.

Built for the **PayPal AI Hackathon 2026** (PayPal sandbox + Gemini).

## How it works

| Step | Who | What happens | PayPal |
|---|---|---|---|
| 1 | Donor | Picks a campaign, donates with the PayPal button | **Orders v2** — captured to the platform account and *held* |
| 2 | Volunteer | Buys the item, sends the receipt + a photo of the item in place (website or Telegram) | — |
| 3 | AI auditor | Reads the receipt (Gemini), converts UAH → USD at the National Bank of Ukraine rate, checks the photo shows the purchased item, checks camera date / GPS / editing software / C2PA, catches reused pictures (perceptual hash) | — |
| 4a | Platform | Proof approved → the tranche goes to the volunteer, donors get the photo | **Payouts v1** |
| 4b | Platform | Volunteer vanished → every held donation goes back | **Refunds v2** |

Everything lands in a public ledger (AG Grid) with the real PayPal transaction ids.

## Try it (judges)

Live demo: **https://proof-of-good.onrender.com** · Telegram: **[@paidup_agent2_bot](https://t.me/paidup_agent2_bot)**
(free hosting — the first visit after a quiet period can take up to a minute to wake the server)

1. **Donate.** Open a campaign, press the PayPal button and log in with the sandbox buyer shown on the page.
   The ledger shows the donation as *held*.
2. **Be the volunteer.** Go to *Volunteer portal*, enter a demo code (`GEN-2026`, `WARM-12`, `PAWS-80`),
   pick a tranche, upload a receipt photo and a photo of the item. The audit takes ~30 s and lists every check.
   - Try a screenshot, a catalogue picture or the same photo twice — the auditor rejects it and says why.
   - A real receipt whose total (in any currency) is close to the tranche amount plus a real photo of the item
     is approved, and the money is paid out to the volunteer's PayPal.
3. **Vanish.** Press *Refund all donors* on the volunteer portal: the campaign closes and PayPal refunds every
   held donation. The ledger shows the refund ids.

Same flow in Telegram: `/code GEN-2026`, then send the receipt and the photo as files.
Donors can `/follow generator` to receive the proof photo the moment money is released.

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
`BOT_USERNAME` (shown on the site), `SANDBOX_BUYER` (test login shown to judges), `ADMIN_KEY`
(enables `POST /api/demo/reset`), `PUBLIC_URL`, `POG_DATA` (data folder), `RUN_BOT` (`0` = website only).
The PayPal app needs **Invoicing off, Payouts on** (Payouts and Refunds are used; no invoicing).

## Code map

```
pog/audit.py    the AI auditor: file facts, receipt reading, NBU rate, photo check, final verdict
pog/service.py  money flow: donation → hold → payout / refund; proof handling; notifications
pog/paypal.py   PayPal REST client (Orders, Payouts, Refunds)
pog/web.py      FastAPI: pages + JSON API
pog/bot.py      Telegram bot for volunteers and donors
pog/store.py    SQLite: campaigns, tranches, donations, proofs, payouts, ledger
static/         the site (vanilla JS, PayPal JS SDK, AG Grid)
```

## AI tools used

- **Gemini 3.5 Flash** (Google AI API): reads receipts, inspects photos, writes the verdict and the donor
  update. Structured JSON output with a schema; `thinkingLevel: low` for speed.
- Perceptual hashing (`imagehash`), EXIF (`Pillow`) and C2PA content credentials (`c2pa-python`) for the
  checks a language model should not be trusted with alone.

## What's real and what's a demo

- All PayPal calls are real sandbox calls; the ids in the ledger can be looked up in the sandbox dashboard.
- Money is captured to the platform's sandbox business account and paid out from its balance — the same
  pattern real fundraising platforms use.
- The AI auditor is strict on purpose: synthetic, screenshot and reused pictures are rejected. A production
  version would add reverse image search and a human review queue for the `review` verdicts.

MIT license.
