from pyrogram import filters
from pyrogram.errors import FloodWait
import asyncio
from shared_client import app
from config import OWNER_ID
from utils.func import (
    unban_user_db,
    unban_all_users_db,
    get_banned_user_ids,
    get_banned_count,
    ban_user_db,
    get_warnings_db,
    reset_warnings_db,
    is_user_banned_db,
    users_collection,
)
from plugins.batch import (
    ACTIVE_USERS,
    save_active_users_to_file,
    Z,
    P,
    PROCESSED_KEYS,
    USER_LOCKS,
    request_batch_cancel,
)
from plugins.ytdl import ongoing_downloads


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

    await message.reply_text(f"✅ Unbanned user: `{user_id}`\n⚠️ Warnings reset too.")
    try:
        await client.send_message(user_id, "✅ You have been unbanned. You can use the bot again.")
    except FloodWait as e:
        await asyncio.sleep(e.value)
        try:
            await client.send_message(user_id, "✅ You have been unbanned. You can use the bot again.")
        except Exception:
            pass
    except Exception:
        pass
    return


@app.on_message(filters.command("killall") & filters.private)
async def killall_cmd(client, message):
    if not message.from_user or not is_owner(message.from_user.id):
        return await message.reply_text("❌ Only owner can use this command.")

    status = await message.reply_text("⏳ Killing all active tasks and notifying users...")

    # 1) Cancel active batches (graceful: stop after current item)
    active_ids = list(ACTIVE_USERS.keys())
    for uid_str in active_ids:
        try:
            await request_batch_cancel(int(uid_str))
        except Exception:
            pass
    try:
        await save_active_users_to_file()
    except Exception:
        pass

    # 2) Clear pending conversational states and progress caches
    Z.clear()
    P.clear()
    PROCESSED_KEYS.clear()
    USER_LOCKS.clear()

    # 3) Reset ytdl in-memory locks so users can retry
    ytdl_users = list(ongoing_downloads.keys())
    ongoing_downloads.clear()

    # 4) Notify all users
    total = 0
    success = 0
    failed = 0
    notify_text = "⚠️ **Bot task reset by admin.**\nPlease retry your command."

    async for doc in users_collection.find({"user_id": {"$exists": True}}, {"user_id": 1, "_id": 0}):
        user_id = doc.get("user_id")
        if not user_id:
            continue
        total += 1
        while True:
            try:
                await client.send_message(int(user_id), notify_text)
                success += 1
                break
            except FloodWait as e:
                await asyncio.sleep(e.value)
            except Exception:
                failed += 1
                break

    await status.edit(
        "✅ **KillAll completed**\n"
        f"Active batches flagged for cancel: `{len(active_ids)}`\n"
        f"YTDL locks cleared: `{len(ytdl_users)}`\n"
        f"Users notified: `{success}/{total}` (failed: {failed})"
    )


@app.on_message(filters.command("unbanall") & filters.private)
async def unban_all_cmd(client, message):
    if not message.from_user or not is_owner(message.from_user.id):
        return await message.reply_text("❌ Only owner can use this command.")

    if len(message.command) < 2 or (message.command[1].lower() != "confirm"):
        return await message.reply_text("⚠️ Use: `/unbanall confirm`", quote=True)

    banned_ids = await get_banned_user_ids()
    removed = await unban_all_users_db()
    await message.reply_text(f"✅ Unbanned all users. Removed bans: `{removed}`")

    for uid in banned_ids:
        try:
            await reset_warnings_db(uid)
            await client.send_message(uid, "✅ You have been unbanned. You can use the bot again.")
        except FloodWait as e:
            await asyncio.sleep(e.value)
            try:
                await client.send_message(uid, "✅ You have been unbanned. You can use the bot again.")
            except Exception:
                pass
        except Exception:
            pass
    return


@app.on_message(filters.command("unbanlist") & filters.private)
async def unban_list_cmd(client, message):
    if not message.from_user or not is_owner(message.from_user.id):
        return await message.reply_text("❌ Only owner can use this command.")

    count = await get_banned_count()
    return await message.reply_text(f"📋 Total banned users: `{count}`")

