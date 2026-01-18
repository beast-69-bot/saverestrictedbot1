

import os
import re
import time
import json
import asyncio
from typing import Dict, Any, Optional, Set, Tuple

from pyrogram import Client, filters
from pyrogram.types import Message

from config import API_ID, API_HASH, LOG_GROUP, STRING, FORCE_SUB, FREEMIUM_LIMIT, PREMIUM_LIMIT, FREE_BATCH_DAILY_LIMIT
from utils.func import get_user_data, screenshot, thumbnail, get_video_metadata, check_and_increment_free_batch_limit
from utils.func import cleanup_temp_file, cleanup_temp_images
from utils.func import get_user_data_key, process_text_with_rules, is_premium_user, E
from shared_client import app as X
from plugins.settings import rename_file
from plugins.start import subscribe as sub
from utils.custom_filters import login_in_progress
from utils.encrypt import dcs

# --------------------------------------------------------------------------
# Keep compatibility with existing globals (other files may import these)
# --------------------------------------------------------------------------
Y = None if not STRING else __import__("shared_client").userbot
Z, P, UB, UC, emp = {}, {}, {}, {}, {}

ACTIVE_USERS = {}
ACTIVE_USERS_FILE = "active_users.json"

# In-memory anti-duplicate (runtime only)
PROCESSED_KEYS: Dict[int, Set[str]] = {}  # uid -> set("chat:msgid")
USER_LOCKS: Dict[int, asyncio.Lock] = {}  # uid -> lock

# --------------------------------------------------------------------------
# Utils
# --------------------------------------------------------------------------
def _lock(uid: int) -> asyncio.Lock:
    if uid not in USER_LOCKS:
        USER_LOCKS[uid] = asyncio.Lock()
    return USER_LOCKS[uid]

def sanitize(filename: str) -> str:
    return re.sub(r'[<>:"/\\|?*\']', "_", filename).strip(" .")[:255]

def load_active_users() -> Dict[str, Dict[str, Any]]:
    try:
        if os.path.exists(ACTIVE_USERS_FILE):
            with open(ACTIVE_USERS_FILE, "r", encoding="utf-8") as f:
                return json.load(f) or {}
    except Exception:
        pass
    return {}

async def save_active_users_to_file() -> None:
    try:
        with open(ACTIVE_USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(ACTIVE_USERS, f)
    except Exception:
        pass

async def add_active_batch(user_id: int, batch_info: Dict[str, Any]) -> None:
    ACTIVE_USERS[str(user_id)] = batch_info
    await save_active_users_to_file()

def is_user_active(user_id: int) -> bool:
    return str(user_id) in ACTIVE_USERS

async def update_batch_progress(user_id: int, current: int, success: int) -> None:
    k = str(user_id)
    if k in ACTIVE_USERS:
        ACTIVE_USERS[k]["current"] = current
        ACTIVE_USERS[k]["success"] = success
        await save_active_users_to_file()

async def request_batch_cancel(user_id: int) -> bool:
    k = str(user_id)
    if k in ACTIVE_USERS:
        ACTIVE_USERS[k]["cancel_requested"] = True
        await save_active_users_to_file()
        return True
    return False

def should_cancel(user_id: int) -> bool:
    k = str(user_id)
    return k in ACTIVE_USERS and bool(ACTIVE_USERS[k].get("cancel_requested", False))

async def remove_active_batch(user_id: int) -> None:
    ACTIVE_USERS.pop(str(user_id), None)
    await save_active_users_to_file()

def get_batch_info(user_id: int) -> Optional[Dict[str, Any]]:
    return ACTIVE_USERS.get(str(user_id))

ACTIVE_USERS = load_active_users()

async def upd_dlg(c: Client) -> bool:
    try:
        async for _ in c.get_dialogs(limit=150):
            pass
        return True
    except Exception:
        return False

async def has_user_login(uid: int) -> bool:
    """
    IMPORTANT: Do NOT change MongoDB keys.
    We only check the existing key: session_string
    """
    ud = await get_user_data(uid)
    return bool(ud and ud.get("session_string"))

# --------------------------------------------------------------------------
# Step 1: Parse Telegram link
# E(link) returns (chat_identifier, msg_id, link_type) in your project
# link_type: 'public' | 'private'
# --------------------------------------------------------------------------
def parse_link(link: str) -> Tuple[Optional[str], Optional[int], Optional[str]]:
    try:
        i, d, lt = E(link)
        return i, int(d) if d else None, lt
    except Exception:
        return None, None, None

# --------------------------------------------------------------------------
# Step 2/3: Resolve correct clients
# --------------------------------------------------------------------------
async def get_ubot(uid: int) -> Optional[Client]:
    bt = await get_user_data_key(uid, "bot_token", None)
    if not bt:
        return None
    if uid in UB:
        return UB.get(uid)
    try:
        bot = Client(f"user_{uid}", bot_token=bt, api_id=API_ID, api_hash=API_HASH)
        await bot.start()
        UB[uid] = bot
        return bot
    except Exception:
        return None

async def get_uclient(uid: int) -> Optional[Client]:
    """
    Returns the user's logged-in Pyrogram client if session exists.
    (Does NOT change login flow or DB keys.)
    """
    if uid in UC:
        return UC.get(uid)

    ud = await get_user_data(uid)
    if not ud:
        return None

    enc = ud.get("session_string")
    if not enc:
        return None

    try:
        ss = dcs(enc)
        cl = Client(
            f"{uid}_client",
            api_id=API_ID,
            api_hash=API_HASH,
            device_model="v3saver",
            session_string=ss,
        )
        await cl.start()
        await upd_dlg(cl)
        UC[uid] = cl
        return cl
    except Exception:
        return None

# --------------------------------------------------------------------------
# Step 3: Fetch message safely
# - public: try bot first, fallback to user session if available
# - private: MUST use user session
# --------------------------------------------------------------------------
async def get_msg(bot_client: Client, user_client: Optional[Client], chat_id: str, msg_id: int, lt: str) -> Optional[Message]:
    try:
        if lt == "public":
            # try bot
            try:
                xm = await bot_client.get_messages(chat_id, msg_id)
                if xm and not getattr(xm, "empty", False):
                    return xm
            except Exception:
                pass
            # fallback to user
            if user_client:
                try:
                    xm = await user_client.get_messages(chat_id, msg_id)
                    if xm and not getattr(xm, "empty", False):
                        return xm
                except Exception:
                    pass
            return None

        # private: must be user_client
        if not user_client:
            return None

        await upd_dlg(user_client)

        # handle -100 / - formats
        s = str(chat_id)
        candidates = []
        if s.startswith("-100"):
            base = s[4:]
            candidates = [s, f"-{base}"]
        elif s.isdigit():
            candidates = [f"-100{s}", f"-{s}", s]
        else:
            candidates = [s]

        for cid in candidates:
            try:
                xm = await user_client.get_messages(cid, msg_id)
                if xm and not getattr(xm, "empty", False):
                    return xm
            except Exception:
                continue

        return None
    except Exception:
        return None

# --------------------------------------------------------------------------
# Progress callback (safe)
# --------------------------------------------------------------------------
async def prog(c, t, C: Client, h: int, m: int, st: float):
    global P
    try:
        if not t:
            return
        p = c / t * 100
        interval = 10 if t >= 100 * 1024 * 1024 else 20 if t >= 50 * 1024 * 1024 else 30 if t >= 10 * 1024 * 1024 else 50
        step = int(p // interval) * interval
        if m not in P or P[m] != step or p >= 100:
            P[m] = step
            c_mb = c / (1024 * 1024)
            t_mb = t / (1024 * 1024)
            bar = "🟢" * int(p / 10) + "🔴" * (10 - int(p / 10))
            elapsed = max(time.time() - st, 0.001)
            speed = c / elapsed / (1024 * 1024)
            eta = time.strftime("%M:%S", time.gmtime((t - c) / (speed * 1024 * 1024))) if speed > 0 else "00:00"
            await C.edit_message_text(
                h,
                m,
                f"__**Pyro Handler...**__\n\n{bar}\n\n"
                f"⚡**__Completed__**: {c_mb:.2f} MB / {t_mb:.2f} MB\n"
                f"📊 **__Done__**: {p:.2f}%\n"
                f"🚀 **__Speed__**: {speed:.2f} MB/s\n"
                f"⏳ **__ETA__**: {eta}\n\n**__Powered by AZ BOTS ADDA__**",
            )
            if p >= 100:
                P.pop(m, None)
    except Exception:
        pass

# --------------------------------------------------------------------------
# Direct send optimization (public only)
# --------------------------------------------------------------------------
async def send_direct(c: Client, m: Message, tcid: int, ft: Optional[str] = None, rtmid: Optional[int] = None) -> bool:
    try:
        if m.video:
            await c.send_video(tcid, m.video.file_id, caption=ft, duration=m.video.duration, width=m.video.width, height=m.video.height, reply_to_message_id=rtmid)
        elif m.video_note:
            await c.send_video_note(tcid, m.video_note.file_id, reply_to_message_id=rtmid)
        elif m.voice:
            await c.send_voice(tcid, m.voice.file_id, reply_to_message_id=rtmid)
        elif m.sticker:
            await c.send_sticker(tcid, m.sticker.file_id, reply_to_message_id=rtmid)
        elif m.audio:
            await c.send_audio(tcid, m.audio.file_id, caption=ft, duration=m.audio.duration, performer=m.audio.performer, title=m.audio.title, reply_to_message_id=rtmid)
        elif m.photo:
            photo_id = m.photo.file_id if hasattr(m.photo, "file_id") else m.photo[-1].file_id
            await c.send_photo(tcid, photo_id, caption=ft, reply_to_message_id=rtmid)
        elif m.document:
            await c.send_document(tcid, m.document.file_id, caption=ft, file_name=m.document.file_name, reply_to_message_id=rtmid)
        else:
            return False
        return True
    except Exception:
        return False

# --------------------------------------------------------------------------
# Step 4/5/6: Process rules → Download → Upload
# --------------------------------------------------------------------------
async def process_msg(bot_client: Client, user_client: Client, msg: Message, did: int, lt: str, uid: int, chat_key: str) -> str:
    try:
        # target config (KEEP key: chat_id)
        cfg_chat = await get_user_data_key(uid, "chat_id", None)
        tcid = did
        rtmid = None
        if cfg_chat:
            try:
                if "/" in str(cfg_chat):
                    a, b = str(cfg_chat).split("/", 1)
                    tcid = int(a)
                    rtmid = int(b) if b else None
                else:
                    tcid = int(cfg_chat)
            except Exception:
                tcid = did
                rtmid = None

        # text/caption rules (KEEP behavior)
        orig_text = msg.caption.markdown if msg.caption else ""
        proc_text = await process_text_with_rules(uid, orig_text)
        user_cap = await get_user_data_key(uid, "caption", "")
        ft = f"{proc_text}\n\n{user_cap}" if proc_text and user_cap else (user_cap if user_cap else proc_text)

        # For PUBLIC: try direct file_id send (no download) if possible
        if lt == "public":
            ok = await send_direct(bot_client, msg, tcid, ft, rtmid)
            if ok:
                return "Sent directly."

        # Download
        st = time.time()
        pmsg = await bot_client.send_message(did, "Downloading...")

        # choose file name safely
        name = str(int(time.time()))
        if msg.video:
            name = sanitize(msg.video.file_name or f"{time.time()}.mp4")
        elif msg.audio:
            name = sanitize(msg.audio.file_name or f"{time.time()}.mp3")
        elif msg.document:
            name = sanitize(msg.document.file_name or f"{time.time()}")
        elif msg.photo:
            name = sanitize(f"{time.time()}.jpg")

        fpath = await user_client.download_media(
            msg,
            file_name=name,
            progress=prog,
            progress_args=(bot_client, did, pmsg.id, st),
        )

        if not fpath or not os.path.exists(fpath):
            try:
                await bot_client.edit_message_text(did, pmsg.id, "Failed.")
            except Exception:
                pass
            return "Failed."

        # Rename rules (only when original filename exists)
        try:
            await bot_client.edit_message_text(did, pmsg.id, "Renaming...")
        except Exception:
            pass

        try:
            if (
                (msg.video and msg.video.file_name)
                or (msg.audio and msg.audio.file_name)
                or (msg.document and msg.document.file_name)
            ):
                fpath = await rename_file(fpath, uid, pmsg)
        except Exception:
            pass

        # Large file route (KEEP old behavior)
        fsize_gb = os.path.getsize(fpath) / (1024 * 1024 * 1024)
        th = thumbnail(uid)

        if fsize_gb > 2 and Y:
            try:
                await bot_client.edit_message_text(did, pmsg.id, "File is larger than 2GB. Using alternative method...")
            except Exception:
                pass

            await upd_dlg(Y)
            mtd = await get_video_metadata(fpath)
            dur, w, h = mtd["duration"], mtd["width"], mtd["height"]
            th = await screenshot(fpath, dur, uid)

            st = time.time()
            sent = await Y.send_document(
                LOG_GROUP,
                fpath,
                thumb=th,
                caption=ft if msg.caption else None,
                progress=prog,
                progress_args=(bot_client, did, pmsg.id, st),
                reply_to_message_id=rtmid,
            )
            await bot_client.copy_message(did, LOG_GROUP, sent.id)
            try:
                os.remove(fpath)
            except Exception:
                pass
            cleanup_temp_file(th, uid)
            try:
                await bot_client.delete_messages(did, pmsg.id)
            except Exception:
                pass
            return "Done (Large file)."

        # Upload
        try:
            await bot_client.edit_message_text(did, pmsg.id, "Uploading...")
        except Exception:
            pass

        st = time.time()
        file_ext = os.path.splitext(fpath)[1].lower()
        video_exts = {".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".webm", ".m4v", ".3gp", ".ogv"}
        audio_exts = {".mp3", ".wav", ".flac", ".aac", ".ogg", ".wma", ".m4a", ".opus", ".aiff", ".ac3"}

        try:
            if msg.video or (msg.document and file_ext in video_exts):
                mtd = await get_video_metadata(fpath)
                dur, w, h = mtd["duration"], mtd["width"], mtd["height"]
                th = await screenshot(fpath, dur, uid)
                await bot_client.send_video(
                    tcid,
                    video=fpath,
                    caption=ft if msg.caption else None,
                    thumb=th,
                    width=w,
                    height=h,
                    duration=dur,
                    progress=prog,
                    progress_args=(bot_client, did, pmsg.id, st),
                    reply_to_message_id=rtmid,
                )
            elif msg.video_note:
                await bot_client.send_video_note(tcid, video_note=fpath, progress=prog, progress_args=(bot_client, did, pmsg.id, st), reply_to_message_id=rtmid)
            elif msg.voice:
                await bot_client.send_voice(tcid, fpath, progress=prog, progress_args=(bot_client, did, pmsg.id, st), reply_to_message_id=rtmid)
            elif msg.sticker:
                await bot_client.send_sticker(tcid, msg.sticker.file_id, reply_to_message_id=rtmid)
            elif msg.audio or (msg.document and file_ext in audio_exts):
                await bot_client.send_audio(tcid, audio=fpath, caption=ft if msg.caption else None, thumb=th, progress=prog, progress_args=(bot_client, did, pmsg.id, st), reply_to_message_id=rtmid)
            elif msg.photo:
                await bot_client.send_photo(tcid, photo=fpath, caption=ft if msg.caption else None, progress=prog, progress_args=(bot_client, did, pmsg.id, st), reply_to_message_id=rtmid)
            elif msg.document:
                await bot_client.send_document(tcid, document=fpath, caption=ft if msg.caption else None, progress=prog, progress_args=(bot_client, did, pmsg.id, st), reply_to_message_id=rtmid)
            elif msg.text:
                await bot_client.send_message(tcid, text=msg.text.markdown, reply_to_message_id=rtmid)
            else:
                await bot_client.send_document(tcid, document=fpath, caption=ft if msg.caption else None, progress=prog, progress_args=(bot_client, did, pmsg.id, st), reply_to_message_id=rtmid)

        except Exception as e:
            try:
                await bot_client.edit_message_text(did, pmsg.id, f"Upload failed: {str(e)[:60]}")
            except Exception:
                pass
            try:
                if os.path.exists(fpath):
                    os.remove(fpath)
            except Exception:
                pass
            return "Failed."

        # cleanup
        try:
            os.remove(fpath)
        except Exception:
            pass
        cleanup_temp_file(th, uid)
        try:
            await bot_client.delete_messages(did, pmsg.id)
        except Exception:
            pass

        return "Done."

    except Exception as e:
        return f"Error: {str(e)[:60]}"

# --------------------------------------------------------------------------
# Command handlers (KEEP commands)
# --------------------------------------------------------------------------
@X.on_message(filters.command(["batch", "single"]))
async def process_cmd(c: Client, m: Message):
    uid = m.from_user.id
    cmd = m.command[0]

    cleanup_temp_images()

    if FREEMIUM_LIMIT == 0 and not await is_premium_user(uid):
        await m.reply_text("This bot does not provide free servies, get subscription from OWNER")
        return

    if cmd == "batch" and not await is_premium_user(uid):
        ok = await check_and_increment_free_batch_limit(uid, FREE_BATCH_DAILY_LIMIT)
        if not ok:
            await m.reply_text(f"Free users can use /batch only {FREE_BATCH_DAILY_LIMIT} times per day.")
            return

    if await sub(c, m) == 1:
        return

    async with _lock(uid):
        pro = await m.reply_text("Doing some checks hold on...")

        if is_user_active(uid):
            await pro.edit("You have an active task. Use /stop to cancel it.")
            return

        ubot = await get_ubot(uid)
        if not ubot:
            await pro.edit("Add your bot with /setbot first")
            return

        Z[uid] = {"step": "start" if cmd == "batch" else "start_single"}
        await pro.edit("Send start link..." if cmd == "batch" else "Send link you want to process.")

@X.on_message(filters.command(["cancel", "stop"]))
async def cancel_cmd(c: Client, m: Message):
    uid = m.from_user.id
    if is_user_active(uid):
        if await request_batch_cancel(uid):
            await m.reply_text("Cancellation requested. Batch will stop after current file completes.")
        else:
            await m.reply_text("Failed to request cancellation.")
        return

    # also cancel any pending conversational state
    if uid in Z:
        Z.pop(uid, None)
        await m.reply_text("Cancelled.")
        return

    await m.reply_text("No active batch process found.")

# --------------------------------------------------------------------------
# Text flow handler
# --------------------------------------------------------------------------
@X.on_message(
    filters.text
    & filters.private
    & ~login_in_progress
    & ~filters.command(
        [
            "start",
            "batch",
            "cancel",
            "login",
            "logout",
            "stop",
            "set",
            "pay",
            "redeem",
            "gencode",
            "single",
            "generate",
            "keyinfo",
            "encrypt",
            "decrypt",
            "keys",
            "setbot",
            "rembot",
        ]
    )
)
async def text_handler(c: Client, m: Message):
    uid = m.from_user.id
    if uid not in Z:
        return

    async with _lock(uid):
        step = Z[uid].get("step")

        ubot = await get_ubot(uid)
        if not ubot:
            await m.reply_text("Add your bot /setbot `token`")
            Z.pop(uid, None)
            return

        # ---------------------------
        # STEP: batch start link
        # ---------------------------
        if step == "start":
            link = m.text.strip()
            i, d, lt = parse_link(link)

            if not i or not d or not lt:
                await m.reply_text("Invalid link format.")
                Z.pop(uid, None)
                return

            # MOST IMPORTANT: private requires login
            if lt == "private" and not await has_user_login(uid):
                await m.reply_text("❌ You must /login first to download from private channels/groups.")
                Z.pop(uid, None)
                return

            Z[uid].update({"step": "count", "cid": i, "sid": d, "lt": lt})
            await m.reply_text("How many messages?")
            return

        # ---------------------------
        # STEP: single link
        # ---------------------------
        if step == "start_single":
            link = m.text.strip()
            i, d, lt = parse_link(link)

            if not i or not d or not lt:
                await m.reply_text("Invalid link format.")
                Z.pop(uid, None)
                return

            # private requires login
            if lt == "private" and not await has_user_login(uid):
                await m.reply_text("❌ You must /login first to download from private channels/groups.")
                Z.pop(uid, None)
                return

            if is_user_active(uid):
                await m.reply_text("Active task exists. Use /stop first.")
                Z.pop(uid, None)
                return

            pt = await m.reply_text("Processing...")

            uc = await get_uclient(uid)  # for private must exist, for public optional
            if lt == "private" and not uc:
                await pt.edit("❌ Login session missing/invalid. Please /login again.")
                Z.pop(uid, None)
                return

            msg = await get_msg(ubot, uc, i, d, lt)
            if not msg:
                await pt.edit("Message not found / deleted / no access.")
                Z.pop(uid, None)
                return

            # Anti-duplicate (runtime)
            seen = PROCESSED_KEYS.setdefault(uid, set())
            key = f"{i}:{d}"
            if key in seen:
                await pt.edit("Already processed (duplicate).")
                Z.pop(uid, None)
                return
            seen.add(key)

            res = await process_msg(ubot, uc or ubot, msg, m.chat.id, lt, uid, i)
            await pt.edit(f"1/1: {res}")
            Z.pop(uid, None)
            return

        # ---------------------------
        # STEP: count for batch
        # ---------------------------
        if step == "count":
            if not m.text.isdigit():
                await m.reply_text("Enter valid number.")
                return

            count = int(m.text)
            maxlimit = PREMIUM_LIMIT if await is_premium_user(uid) else FREEMIUM_LIMIT
            if count > maxlimit:
                await m.reply_text(f"Maximum limit is {maxlimit}.")
                return

            i, start_id, lt = Z[uid]["cid"], int(Z[uid]["sid"]), Z[uid]["lt"]

            # private requires login
            if lt == "private" and not await has_user_login(uid):
                await m.reply_text("❌ You must /login first to download from private channels/groups.")
                Z.pop(uid, None)
                return

            uc = await get_uclient(uid)
            if lt == "private" and not uc:
                await m.reply_text("❌ Login session missing/invalid. Please /login again.")
                Z.pop(uid, None)
                return

            if is_user_active(uid):
                await m.reply_text("Active task exists. Use /stop first.")
                Z.pop(uid, None)
                return

            pt = await m.reply_text("Processing batch...")

            await add_active_batch(
                uid,
                {
                    "total": count,
                    "current": 0,
                    "success": 0,
                    "cancel_requested": False,
                    "progress_message_id": pt.id,
                },
            )

            success = 0
            seen = PROCESSED_KEYS.setdefault(uid, set())

            try:
                for j in range(count):
                    if should_cancel(uid):
                        try:
                            await pt.edit(f"Cancelled at {j}/{count}. Success: {success}")
                        except Exception:
                            pass
                        break

                    await update_batch_progress(uid, j, success)
                    mid = start_id + j

                    key = f"{i}:{mid}"
                    if key in seen:
                        continue
                    seen.add(key)

                    msg = await get_msg(ubot, uc, i, mid, lt)
                    if not msg:
                        # deleted/expired/no access -> skip
                        try:
                            await pt.edit(f"{j+1}/{count}: Skipped (not found/access). ✅ {success}")
                        except Exception:
                            pass
                        await asyncio.sleep(2)
                        continue

                    res = await process_msg(ubot, uc or ubot, msg, m.chat.id, lt, uid, i)
                    if "Done" in res or "Sent" in res or "Copied" in res:
                        success += 1

                    try:
                        await pt.edit(f"{j+1}/{count}: {res} | ✅ {success}")
                    except Exception:
                        pass

                    await asyncio.sleep(3)

                if not should_cancel(uid):
                    await m.reply_text(f"Batch Completed ✅ Success: {success}/{count}")

            finally:
                await remove_active_batch(uid)
                Z.pop(uid, None)
            return
