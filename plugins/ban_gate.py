from pyrogram import filters, StopPropagation
from shared_client import app
from utils.func import is_user_banned_db

@app.on_message(
    (filters.private | filters.group)
    & filters.incoming
    & ~filters.bot,
    group=-2
)
async def global_ban_gate(client, message):
    if not message.from_user:
        return

    if await is_user_banned_db(message.from_user.id):
        cfg = __import__("config")
        contact = getattr(cfg, "ADMIN_CONTACT", "")
        await message.reply_text(
            f"⛔ You are banned.\nContact admins: {contact}"
        )
        raise StopPropagation
