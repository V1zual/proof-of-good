"""Telegram bot: volunteers send the evidence from the field, donors get updates when money moves."""
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
HELP = ("I'm <b>Proof of Good</b>. Donations wait on PayPal and reach the volunteer one tranche at a time; every "
        "payment from the volunteer's campaign card is checked, and the next tranche comes only after a photo proves "
        "the last one.\n\n"
        "🙋 <b>Volunteer?</b> Send /code and your campaign code (e.g. <code>/code GEN-2026</code>).\n"
        "💙 <b>Donor?</b> Send /follow and the campaign id (e.g. <code>/follow generator</code>) to get the photos.")
ICON = {"waiting": "⏳", "released": "💳", "accounted": "✅"}


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
                                    "\n\nPay only with your campaign card. When the item is in place, send me its "
                                    "<b>photo</b> (as a <i>file</i>, so the camera date stays) — and the receipt too "
                                    "if a payment was unclear.")


def _status_text(cid: str) -> str:
    c, tot = store.campaign(cid), store.totals(cid)
    lines = [f"💳 {html.escape(c['card_label'] or 'card')} · raised {service.money(tot['raised'])} of "
             f"{service.money(tot['goal'])} · {service.money(tot['held'])} held"]
    if c["status"] == "frozen":
        lines.append(f"⛔ Frozen: {html.escape(c['frozen_reason'] or '')}")
    for t in store.tranches(cid):
        extra = f" — spent {service.money(store.spent(t['id']))}" if t["status"] == "released" else ""
        lines.append(f"{ICON.get(t['status'], '•')} {html.escape(t['title'])} — {service.money(t['amount'])}{extra}")
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
    await update.message.reply_html(f"💙 You follow «{html.escape(c['title'])}». I'll tell you when money is released "
                                    f"and send the photo when it is proven spent.")


async def on_image(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    cid = ctx.user_data.get("campaign")
    if not cid:
        return await msg.reply_html("Link your campaign first: <code>/code YOUR-CODE</code>")
    doc = msg.document
    if doc and not (doc.mime_type or "").startswith("image/"):
        return await msg.reply_html("Please send an image (JPEG or PNG).")
    data = bytes(await (await (doc or msg.photo[-1]).get_file()).download_as_bytearray())
    images = ctx.user_data.setdefault("images", [])
    images[:] = (images + [data])[-2:]
    note = "" if doc else "\nℹ️ Sent compressed — the camera date is lost; send as a file next time."
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔍 Audit now", callback_data="audit")]])
    text = ("📷 Got the photo. If a card payment was unclear, send the receipt too — or audit now." if len(images) == 1
            else "🧾 Got the photo and the receipt.")
    await msg.reply_html(text + note, reply_markup=kb)


async def on_audit(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    cid = ctx.user_data.get("campaign")
    images = ctx.user_data.get("images") or []
    tr = store.current_tranche(cid) if cid else None
    if not images:
        return await q.edit_message_text("Send the photo first.")
    if not tr:
        return await q.edit_message_text("No tranche is on your card right now — nothing to account for.")
    ctx.user_data["images"] = []
    await q.edit_message_text("🔍 <b>Auditing…</b>", parse_mode=ParseMode.HTML)
    await ctx.bot.send_chat_action(q.message.chat_id, ChatAction.TYPING)
    lines, last = [], [0.0]

    async def step(e: dict):
        line = _step_line(e)
        if line:
            lines.append(line)
        if time.time() - last[0] > 1.0 or e["kind"] in ("verdict", "release"):
            last[0] = time.time()
            try:
                await q.edit_message_text("🔍 <b>Auditing</b>\n" + "\n".join(lines[-16:]), parse_mode=ParseMode.HTML)
            except Exception:
                pass  # "message is not modified" or rate limit — the next step redraws it

    try:
        v = await service.submit_evidence(tr["id"], images[0], images[1] if len(images) > 1 else None, "telegram", step)
    except Exception as ex:
        log.exception("evidence")
        return await q.message.reply_html(f"⚠️ {html.escape(str(ex)[:300])}")
    await q.message.reply_html(service.volunteer_text(store.tranche(tr["id"]), v))


def _step_line(e: dict) -> str:
    esc = html.escape
    if e["kind"] == "stage":
        return f"⏳ {esc(e['name'])}…"
    if e["kind"] == "check":
        mark = {True: "✔", False: "✖", None: "·"}[e["ok"]]
        return f"{mark} {esc(e['name'])} — {esc(e['detail'][:70])}"
    if e["kind"] == "verdict":
        return f"<b>→ {'accounted ✅' if e.get('accounted') else esc(e['decision'])}</b>"
    if e["kind"] == "release":
        return f"💸 next tranche: <b>{service.money(e['amount'])}</b> for «{esc(e['tranche'])}»"
    return ""


def build() -> Application:
    app = Application.builder().token(config.secret("TELEGRAM_BOT_TOKEN")).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("code", code))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("follow", follow))
    app.add_handler(CommandHandler("help", lambda u, c: u.message.reply_html(HELP)))
    app.add_handler(CallbackQueryHandler(on_audit, pattern=r"^audit$"))
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
