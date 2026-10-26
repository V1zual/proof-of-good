"""Telegram bot: volunteers send proofs from the field, donors get photo updates when money is released."""
import asyncio
import html
import logging
import time

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler,
                          filters)

from . import config, notify, service, store

log = logging.getLogger("pog.bot")
HELP = ("I'm <b>Proof of Good</b>. Donations are held on PayPal until the volunteer proves the purchase and "
        "the AI auditor approves it.\n\n"
        "🙋 <b>Volunteer?</b> Send /code and your campaign code (e.g. <code>/code GEN-2026</code>).\n"
        "💙 <b>Donor?</b> Send /follow and the campaign id (e.g. <code>/follow generator</code>) to get a "
        "photo update the moment the money is released.")


async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    arg = (ctx.args or [""])[0]
    if arg.startswith("vol_"):
        return await _link_volunteer(update, ctx, arg[4:])
    if arg.startswith("follow_"):
        return await _follow(update, arg[7:])
    await update.message.reply_html(HELP)


async def code(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        return await update.message.reply_html("Send the code like this: <code>/code GEN-2026</code>")
    await _link_volunteer(update, ctx, ctx.args[0])


async def _link_volunteer(update: Update, ctx: ContextTypes.DEFAULT_TYPE, code: str):
    c = store.campaign_by_code(code)
    if not c:
        return await update.message.reply_html("I don't know this code. Check it on your campaign page.")
    store.set_campaign(c["id"], volunteer_chat=update.effective_chat.id)
    ctx.user_data.clear()
    ctx.user_data["campaign"] = c["id"]
    await update.message.reply_html(f"👋 {html.escape(c['volunteer_name'])}, you're linked to "
                                    f"«{html.escape(c['title'])}».\n\n" + _status_text(c["id"]) +
                                    "\n\nTo claim a tranche: send the <b>receipt</b> photo, then the <b>photo of the "
                                    "item in place</b>. Send them as <i>files</i> (without compression) so I can "
                                    "read the camera date.")


def _status_text(cid: str) -> str:
    tot = store.totals(cid)
    icons = {"waiting": "⏳", "checking": "🔄", "verified": "✅", "rejected": "⛔", "review": "🔎", "paid": "💸"}
    lines = [f"Raised {service.money(tot['raised'])} of {service.money(tot['goal'])}, "
             f"{service.money(tot['held'])} held, {service.money(tot['paid'])} paid out."]
    for t in store.tranches(cid):
        lines.append(f"{icons.get(t['status'], '•')} {html.escape(t['title'])} — {service.money(t['amount'])}")
    return "\n".join(lines)


async def status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cid = ctx.user_data.get("campaign")
    if not cid:
        return await update.message.reply_html("Link your campaign first: <code>/code YOUR-CODE</code>")
    await update.message.reply_html(_status_text(cid))


async def follow(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        names = "\n".join(f"• <code>/follow {c['id']}</code> — {html.escape(c['title'])}" for c in store.campaigns())
        return await update.message.reply_html("Which campaign?\n" + names)
    await _follow(update, ctx.args[0])


async def _follow(update: Update, cid: str):
    c = store.campaign(cid)
    if not c:
        return await update.message.reply_html("No such campaign.")
    store.follow(cid, update.effective_chat.id)
    await update.message.reply_html(f"💙 You follow «{html.escape(c['title'])}». I'll send you the photo and the "
                                    f"receipt summary the moment donors' money is released.")


async def on_image(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    cid = ctx.user_data.get("campaign")
    if not cid:
        return await msg.reply_html("Link your campaign first: <code>/code YOUR-CODE</code>")
    doc = msg.document
    if doc and not (doc.mime_type or "").startswith("image/"):
        return await msg.reply_html("Please send an image (JPEG or PNG).")
    tg_file = await (doc or msg.photo[-1]).get_file()
    data = bytes(await tg_file.download_as_bytearray())
    pending = ctx.user_data.setdefault("images", [])
    pending.append(data)
    if len(pending) == 1:
        return await msg.reply_html("📄 Got the receipt. Now send the photo of the item in place.")
    if msg.photo and not doc:
        await msg.reply_html("ℹ️ Sent as a compressed photo — camera metadata is gone, the audit will note it.")
    open_tranches = [t for t in store.tranches(cid) if t["status"] in ("waiting", "rejected", "review")]
    if not open_tranches:
        ctx.user_data["images"] = []
        return await msg.reply_html("Every tranche is already verified or paid. 🎉")
    kb = InlineKeyboardMarkup([[InlineKeyboardButton(f"{t['title'][:40]} — {service.money(t['amount'])}",
                                                     callback_data=f"tr:{t['id']}")] for t in open_tranches])
    await msg.reply_html("📸 Got both. Which tranche is this proof for?", reply_markup=kb)


async def on_pick(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    tid = q.data.split(":", 1)[1]
    images = ctx.user_data.get("images") or []
    if len(images) < 2:
        return await q.edit_message_text("Send the receipt and the photo first.")
    ctx.user_data["images"] = []
    await q.edit_message_text("🔍 <b>Auditing…</b>", parse_mode=ParseMode.HTML)
    await ctx.bot.send_chat_action(q.message.chat_id, ChatAction.TYPING)
    lines, last = [], [0.0]

    async def step(e: dict):
        line = _step_line(e)
        if line:
            lines.append(line)
        if time.time() - last[0] > 1.0 or e["kind"] in ("verdict", "payout"):
            last[0] = time.time()
            try:
                await q.edit_message_text("🔍 <b>Auditing</b>\n" + "\n".join(lines[-16:]), parse_mode=ParseMode.HTML)
            except Exception:
                pass  # "message is not modified" or rate limit — the next step redraws it

    try:
        v = await service.submit_proof(tid, images[0], images[1], "telegram", step)
    except Exception as ex:
        log.exception("proof")
        return await q.message.reply_html(f"⚠️ {html.escape(str(ex)[:300])}")
    await q.message.reply_html(service._volunteer_text(store.tranche(tid), v))


def _step_line(e: dict) -> str:
    esc = html.escape
    if e["kind"] == "stage":
        return f"⏳ {esc(e['name'])}…"
    if e["kind"] == "check":
        mark = {True: "✔", False: "✖", None: "·"}[e["ok"]]
        return f"{mark} {esc(e['name'])} — {esc(e['detail'][:70])}"
    if e["kind"] == "verdict":
        return f"<b>→ {esc(e['decision'])}</b>"
    if e["kind"] == "payout":
        return f"💸 <b>{service.money(e['amount'])}</b> sent with PayPal Payouts ({esc(e['batch'])})"
    return ""


def build() -> Application:
    app = Application.builder().token(config.secret("TELEGRAM_BOT_TOKEN")).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("code", code))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("follow", follow))
    app.add_handler(CommandHandler("help", lambda u, c: u.message.reply_html(HELP)))
    app.add_handler(CallbackQueryHandler(on_pick, pattern=r"^tr:"))
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.IMAGE, on_image))
    return app


async def run_in_background():
    """Runs the bot inside the web server's event loop (one process on the host)."""
    app = build()
    notify.bot = app.bot
    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)
    log.info("telegram bot polling")
    try:
        await asyncio.Event().wait()
    finally:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()
