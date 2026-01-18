from pyrogram import filters
from shared_client import app
from config import OWNER_ID
from utils.func import unban_user_db, ban_user_db, get_warnings_db, reset_warnings_db, is_user_banned_db

def is_owner(uid: int) -> bool:
    if isinstance(OWNER_ID, (list, tuple, set)):
        return uid in OWNER_ID
    return uid == OWNER_ID

@app.on_message(filters.command("unban") & filters.private)
async def unban_cmd(client, message):
    if not message.from_user or not is_owner(message.from_user.id):
        return await message.reply_text("❌ Only owner can use this command.")

    if len(message.command) < 2:
        return await message.reply_text("✅ Use: `/unban user_id`", quote=True)

    try:
        user_id = int(message.command[1])
    except Exception:
        return await message.reply_text("❌ Invalid user_id. Example: `/unban 123456789`")

    await unban_user_db(user_id)
    await reset_warnings_db(user_id)  # optional: warning reset too

    return await message.reply_text(f"✅ Unbanned user: `{user_id}`\n⚠️ Warnings reset too.")
