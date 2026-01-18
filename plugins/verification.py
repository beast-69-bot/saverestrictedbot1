# plugins/verify.py
# DB-based token verification with TTL (works even after restart)

import os
import string
import random
import logging
import asyncio
from time import time

from urllib3 import disable_warnings
from cloudscraper import create_scraper
from motor.motor_asyncio import AsyncIOMotorClient

from pyrogram import filters, StopPropagation
from pyrogram.errors import FloodWait
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message

from shared_client import app  # IMPORTANT: use the same app your bot runs on
from config import MONGO_DB as DATABASE_URL, OWNER_ID, LOG_GROUP

from utils.func import is_premium_user, add_warning_db, ban_user_db

import re


logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# ENV / CONFIG
# ─────────────────────────────────────────────
VERIFY_PHOTO = os.environ.get("VERIFY_PHOTO", "https://files.catbox.moe/uld6uo.jpg")
SHORTLINK_SITE = os.environ.get("SHORTLINK_SITE", "caslinks.com")
SHORTLINK_API = os.environ.get("SHORTLINK_API", "05b01394bd9824e3f76ff2191417922006c97dbf")  # set in env
VERIFY_TUTORIAL = os.environ.get("VERIFY_TUTORIAL", "https://t.me/aztutorial12321/32")

VERIFY_EXPIRE = int(float(os.environ.get("VERIFY_EXPIRE", 86400)))  # user verified duration
TOKEN_TTL = int(float(os.environ.get("TOKEN_TTL", 300)))            # token ttl
MIN_TOKEN_AGE = int(float(os.environ.get("MIN_TOKEN_AGE", 60)))     # anti bypass

COLLECTION_NAME = os.environ.get("COLLECTION_NAME", "tokencollect")
TOKEN_COLLECTION = os.environ.get("TOKEN_COLLECTION", "verify_tokens")

PREMIUM_USERS = (
    list(map(int, os.environ.get("PREMIUM_USERS", "").split()))
    if os.environ.get("PREMIUM_USERS")
    else []
)

# ─────────────────────────────────────────────
# DB LAYER
# ─────────────────────────────────────────────
class VerifyDB:
    def __init__(self):
        self._dbclient = AsyncIOMotorClient(DATABASE_URL)
        self._db = self._dbclient["verify-db"]
        self._verifydb = self._db[COLLECTION_NAME]
        self._tokendb = self._db[TOKEN_COLLECTION]
        try:
            self._tokendb.create_index("expireAt", expireAfterSeconds=0)
        except Exception:
            pass

        logger.info(
            "VerifyDB connected | db=verify-db | verify_col=%s | token_col=%s",
            COLLECTION_NAME, TOKEN_COLLECTION
        )

    async def get_verify_status(self, user_id: int) -> float:
        doc = await self._verifydb.find_one({"id": user_id})
        return float(doc.get("verify_status", 0)) if doc else 0.0

    async def update_verify_status(self, user_id: int):
        await self._verifydb.update_one(
            {"id": user_id},
            {"$set": {"verify_status": time()}},
            upsert=True
        )

    async def save_token(self, user_id: int, token: str, short_url: str):
        now = int(time())
        expire_at = now + TOKEN_TTL
        await self._tokendb.update_one(
            {"user_id": user_id},
            {"$set": {
                "user_id": user_id,
                "token": token,
                "short_url": short_url,
                "createdAt": now,
                "expireAt": expire_at
            }},
            upsert=True
        )

    async def get_token(self, user_id: int):
        return await self._tokendb.find_one({"user_id": user_id})

    async def delete_token(self, user_id: int):
        await self._tokendb.delete_one({"user_id": user_id})


verifydb = VerifyDB()

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def get_readable_time(seconds: int) -> str:
    seconds = int(seconds)
    if seconds <= 0:
        return "0s"
    periods = [("d", 86400), ("h", 3600), ("m", 60), ("s", 1)]
    out = ""
    for name, sec in periods:
        if seconds >= sec:
            val, seconds = divmod(seconds, sec)
            out += f"{int(val)}{name}"
    return out or "0s"


async def is_user_verified(user_id: int) -> bool:
    try:
        if await is_premium_user(user_id):
            return True
    except Exception:
        pass

    if user_id in PREMIUM_USERS:
        return True

    if VERIFY_EXPIRE <= 0:
        return True

    last = await verifydb.get_verify_status(user_id)
    if not last:
        return False

    return (time() - last) < VERIFY_EXPIRE


async def get_short_url(longurl: str, shortener_site=SHORTLINK_SITE, shortener_api=SHORTLINK_API) -> str:
    if not shortener_api:
        return longurl

    cget = create_scraper().request
    disable_warnings()

    url = f"https://{shortener_site}/api"
    params = {"api": shortener_api, "url": longurl, "format": "text"}

    try:
        res = cget("GET", url, params=params)
        if res is not None and getattr(res, "status_code", None) == 200:
            txt = (res.text or "").strip()
            if txt:
                return txt

        params["format"] = "json"
        res = cget("GET", url, params=params)
        data = res.json() if res is not None else {}
        if isinstance(data, dict):
            for key in ("shortenedUrl", "short", "url", "result"):
                if data.get(key):
                    return data[key]
    except Exception as e:
        logger.exception("Shortlink failed: %s", e)

    return longurl


async def get_verify_token(user_id: int, base_start_link: str) -> str:
    doc = await verifydb.get_token(user_id)
    if doc and doc.get("short_url") and int(doc.get("expireAt", 0)) > int(time()):
        return doc["short_url"]

    token = "".join(random.choices(string.ascii_letters + string.digits, k=9))
    long_link = f"{base_start_link}verify-{user_id}-{token}"
    short_url = await get_short_url(long_link)
    await verifydb.save_token(user_id, token, short_url)

    logger.info("Token generated | user=%s | token=%s", user_id, token)
    return short_url


async def send_verification(client, message, text: str | None = None):
    me = await client.get_me()
    username = me.username or ""

    if await is_user_verified(message.from_user.id):
        text = f"<b>Hi 👋 {message.from_user.mention}\nYou are already verified ✅</b>"
        buttons = None
    else:
        start_link = f"https://telegram.me/{username}?start="
        verify_url = await get_verify_token(message.from_user.id, start_link)
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("Get Token", url=verify_url)],
            [InlineKeyboardButton("🎬 Tutorial 🎬", url=VERIFY_TUTORIAL)]
        ])

    if not text:
        text = (
            f"<b>⛔ Token Expired!</b>\n\n"
            f"👋 Hi {message.from_user.mention},\n"
            f"<blockquote expandable>\n"
            f"Your access token has expired.\n"
            f"Please generate a new token to continue using the bot.\n\n"
            f"⏳ <b>Access Duration:</b> {get_readable_time(VERIFY_EXPIRE)}\n"
            f"</blockquote>\n"
            f"#Verification ⌛"
        )

    msg_obj = message if isinstance(message, Message) else message.message
    await client.send_photo(
        chat_id=msg_obj.chat.id,
        photo=VERIFY_PHOTO,
        caption=text,
        reply_markup=buttons,
        reply_to_message_id=msg_obj.id,
    )


async def notify_admins(client, text: str):
    # LOG_GROUP
    try:
        if LOG_GROUP:
            await client.send_message(LOG_GROUP, text)
    except Exception:
        pass

    # OWNER_ID
    try:
        owners = OWNER_ID if isinstance(OWNER_ID, list) else [OWNER_ID]
        for oid in owners:
            try:
                await client.send_message(int(oid), text)
            except FloodWait as e:
                await asyncio.sleep(e.value)
                await client.send_message(int(oid), text)
            except Exception:
                pass
    except Exception:
        pass


async def validate_token(client, message, data: str):
    user_id = message.from_user.id

    if await is_user_verified(user_id):
        await message.reply("<b>You are already verified ✅</b>")
        return

    # expecting: verify-<uid>-<token>
    try:
        prefix, uid, token = data.split("-", 2)
        if prefix != "verify":
            raise ValueError("bad prefix")
    except Exception:
        await send_verification(client, message, text="<b>Invalid verify format. Tap Get Token again.</b>")
        return

    if uid != str(user_id):
        await send_verification(client, message, text="<b>User mismatch ❌ Tap Get Token again.</b>")
        return

    doc = await verifydb.get_token(user_id)
    if not doc:
        await send_verification(client, message, text="<b>Token not found/expired. Tap Get Token again.</b>")
        return

    if int(doc.get("expireAt", 0)) <= int(time()):
        await verifydb.delete_token(user_id)
        await send_verification(client, message, text="<b>Token expired. Tap Get Token again.</b>")
        return

    # anti bypass
    try:
        now = int(time())
        created_at = int(doc.get("createdAt", 0))
        age = now - created_at
    except Exception:
        age = None

    if age is not None and age < MIN_TOKEN_AGE:
        warn_count = await add_warning_db(user_id, reason=f"Bypass attempt: token used too fast age={age}s")

        u = message.from_user
        uname = f"@{u.username}" if u and u.username else "NoUsername"
        full = f"{u.first_name or ''} {u.last_name or ''}".strip() if u else "Unknown"
        chat = message.chat

        admin_text = (
            "🚨 **BYPASS WARNING DETECTED**\n\n"
            f"👤 **User:** {full}\n"
            f"🔗 **Username:** {uname}\n"
            f"🆔 **User ID:** `{user_id}`\n"
            f"💬 **Chat:** `{chat.id}` ({chat.type})\n"
            f"⏱ **Token Age:** `{age}s` (MIN={MIN_TOKEN_AGE}s)\n"
            f"⚠️ **Warnings:** `{warn_count}/3`\n"
        )
        await notify_admins(client, admin_text)

        if warn_count >= 3:
            await ban_user_db(user_id, reason="Auto-ban: 3 bypass warnings", banned_by=0)
            await notify_admins(client, f"⛔ **AUTO-BAN**: `{user_id}` (3 bypass warnings)")

            await verifydb.delete_token(user_id)
            await message.reply_text("⛔ You are permanently banned for bypass attempts.\nContact admins if you think this is a mistake.")
            raise StopPropagation

        await verifydb.delete_token(user_id)
        warn_text = (
            f"<b>🚫 रुक जाओ!</b>\n\n"
            f"Bypass detect ho gaya.\n"
            f"⚠️ Warning: <b>{warn_count}/3</b>\n\n"
            f"Ab फिर से <b>Get Token</b> दबाकर properly verify करो.\n"
            f"<b>3 warnings पर direct ban!</b>"
        )
        await send_verification(client, message, text=warn_text)
        raise StopPropagation

    if doc.get("token") != token:
        await send_verification(client, message, text="<b>Invalid token. Tap Get Token again.</b>")
        return

    # success
    await verifydb.delete_token(user_id)
    await verifydb.update_verify_status(user_id)

    await client.send_photo(
        chat_id=message.from_user.id,
        photo=VERIFY_PHOTO,
        caption=(
            f"<b>✅ Verification Successful!</b>\n\n"
            f"👋 Welcome back, {message.from_user.mention}!\n"
            f"🚀 You now have full access to the bot.\n\n"
            f"⏳ <b>Access valid for:</b> {get_readable_time(VERIFY_EXPIRE)}"
        ),
        reply_to_message_id=message.id,
    )

    logger.info("User verified ✅ | user=%s", user_id)


# ─────────────────────────────────────────────
# GLOBAL GATE
# ─────────────────────────────────────────────
async def token_system_filter(_, __, message):
    if message.from_user is None:
        return False
    if await is_user_verified(message.from_user.id):
        return False
    return True


@app.on_message(
    (filters.private | filters.group)
    & filters.incoming
    & filters.text
    & filters.regex(r"^/")
    & ~filters.regex(r"^/(help|pay)(\s|$)")
    & filters.create(token_system_filter)
    & ~filters.bot,
    group=-1
)
async def global_verify_function(client, message):
    if message.text:
        parts = message.text.split()
        if len(parts) == 2 and parts[1].startswith("verify-"):
            await validate_token(client, message, parts[1])
            raise StopPropagation

    await send_verification(client, message)
    raise StopPropagation


# Callbacks allowed WITHOUT token
ALLOWED_CALLBACKS = (
    r"^help_",        # help_prev_0, help_next_0
    r"^see_plan$",
    r"^see_terms$",
    r"^p_",          # ✅ /pay buttons (p_d, p_w, p_m)
)

@app.on_callback_query(group=-1)
async def global_verify_callback_gate(client, cq):
    if not cq.from_user:
        return

    data = cq.data or ""

    # ✅ allow help & pay buttons
    for pat in ALLOWED_CALLBACKS:
        if re.match(pat, data):
            return

    # ✅ allow verified users
    if await is_user_verified(cq.from_user.id):
        return

    # ❌ block others
    try:
        await cq.answer(
            "Token required. Please verify first ✅",
            show_alert=True
        )
    except Exception:
        pass

    if cq.message:
        await send_verification(client, cq.message)

    raise StopPropagation
