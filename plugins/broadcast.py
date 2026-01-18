


import asyncio
import logging

from telethon import events
from telethon.errors import FloodWaitError

from config import OWNER_ID
from shared_client import client as bot_client
from utils.func import is_private_chat, users_collection

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger("teamspy.broadcast")


@bot_client.on(events.NewMessage(pattern=r"^/broadcast(?:\s+(.+))?$"))
async def broadcast_handler(event):
    if not await is_private_chat(event):
        await event.respond("This command can only be used in private chats.")
        return
    if event.sender_id not in OWNER_ID:
        return

    text = event.pattern_match.group(1)
    reply = await event.get_reply_message()
    if not text and not reply:
        await event.respond("Usage: /broadcast <message> or reply to a message.")
        return

    status = await event.respond("📣 Broadcast started...")
    total = 0
    success = 0
    failed = 0

    async for doc in users_collection.find(
        {"user_id": {"$exists": True}}, {"user_id": 1, "_id": 0}
    ):
        user_id = doc.get("user_id")
        if not user_id:
            continue
        total += 1

        while True:
            try:
                if reply:
                    await bot_client.forward_messages(user_id, reply)
                else:
                    await bot_client.send_message(user_id, text)
                success += 1
                break
            except FloodWaitError as exc:
                await asyncio.sleep(exc.seconds)
            except Exception as exc:
                failed += 1
                logger.warning("Broadcast failed for %s: %s", user_id, exc)
                break

    await status.edit(
        "✅ Broadcast completed.\n"
        f"Total users: {total}\n"
        f"Success: {success}\n"
        f"Failed: {failed}"
    )
