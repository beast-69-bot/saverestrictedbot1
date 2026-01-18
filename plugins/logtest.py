from pyrogram import filters
from shared_client import app
from config import OWNER_ID, LOG_GROUP


def is_owner(uid: int) -> bool:
    if isinstance(OWNER_ID, (list, tuple, set)):
        return uid in OWNER_ID
    return uid == OWNER_ID


@app.on_message(filters.command("logtest") & filters.private)
async def logtest_cmd(client, message):
    if not message.from_user or not is_owner(message.from_user.id):
        return await message.reply_text("Only owner can use this command.")

    try:
        await client.send_message(LOG_GROUP, f"Log test from {message.from_user.id}")
        await message.reply_text("Sent a test log message to LOG_GROUP.")
    except Exception as e:
        await message.reply_text(f"Failed to send log message: {e}")
