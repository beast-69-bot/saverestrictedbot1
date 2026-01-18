
import concurrent.futures
import time
import os
import re
import cv2
import logging
import asyncio
from datetime import datetime, timedelta
from motor.motor_asyncio import AsyncIOMotorClient
from config import MONGO_DB as MONGO_URI, DB_NAME

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

PUBLIC_LINK_PATTERN = re.compile(r'(https?://)?(t\.me|telegram\.me)/([^/]+)(/(\d+))?')
PRIVATE_LINK_PATTERN = re.compile(r'(https?://)?(t\.me|telegram\.me)/c/(\d+)(/(\d+))?')
VIDEO_EXTENSIONS = {"mp4", "mkv", "avi", "mov", "wmv", "flv", "webm", "mpeg", "mpg", "3gp"}

mongo_client = AsyncIOMotorClient(MONGO_URI)
db = mongo_client[DB_NAME]
users_collection = db["users"]
premium_users_collection = db["premium_users"]
statistics_collection = db["statistics"]
codedb = db["redeem_code"]

# ------- < start > Session Encoder don't change -------

a1 = "YXpfYm90c19zb2x1dGlvbg=="
a2 = "Mg=="
a3 = "Z2V0X21lc3NhZ2Vz" 
a4 = "cmVwbHlfcGhvdG8=" 
a5 = "c3RhcnQ="
attr1 = "cGhvdG8="
attr2 = "ZmlsZV9pZA=="
a7 = "SGkg8J+RiyBXZWxjb21lIQoK4oCiIFNhdmUgcG9zdHMgZnJvbSBwdWJsaWMgY2hhbm5lbHMgJiBncm91cHMK4oCiIERvd25sb2FkIHZpZGVvcy9hdWRpbyBmcm9tIFlULCBJbnN0YSAmIG1vcmUK4oCiIEp1c3Qgc2VuZCB0aGUgcG9zdCBsaW5rCgpGb3IgcHJpdmF0ZSBjaGFubmVscywgL2xvZ2luIGZpcnN0LgpVc2UgL2hlbHAgdG8ga25vdyBtb3JlLg=="
a8 = "Sm9pbiBDaGFubmVs"
a9 = "R2V0IFByZW1pdW0=" 
a10 = "aHR0cHM6Ly90Lm1lL3RlYW1fc3B5X3Bybw==" 
a11 = "aHR0cHM6Ly90Lm1lL2tpbmdvZnBhdGFs" 

# ------- < end > Session Encoder don't change --------

def is_private_link(link):
    return bool(PRIVATE_LINK_PATTERN.match(link))


def thumbnail(sender):
    return f'{sender}.jpg' if os.path.exists(f'{sender}.jpg') else None


def hhmmss(seconds):
    return time.strftime('%H:%M:%S', time.gmtime(seconds))


def E(L):   
    private_match = re.match(r'https://t\.me/c/(\d+)/(?:\d+/)?(\d+)', L)
    public_match = re.match(r'https://t\.me/([^/]+)/(?:\d+/)?(\d+)', L)
    
    if private_match:
        return f'-100{private_match.group(1)}', int(private_match.group(2)), 'private'
    elif public_match:
        return public_match.group(1), int(public_match.group(2)), 'public'
    
    return None, None, None


def get_display_name(user):
    if user.first_name and user.last_name:
        return f"{user.first_name} {user.last_name}"
    elif user.first_name:
        return user.first_name
    elif user.last_name:
        return user.last_name
    elif user.username:
        return user.username
    else:
        return "Unknown User"

async def track_user(user):
    if not user:
        return
    now = datetime.now()
    await users_collection.update_one(
        {"user_id": user.id},
        {
            "$set": {
                "user_id": user.id,
                "username": user.username,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "updated_at": now,
            },
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
    )


def sanitize_filename(filename):
    return re.sub(r'[<>:"/\\|?*]', '_', filename)


def get_dummy_filename(info):
    file_type = info.get("type", "file")
    extension = {
        "video": "mp4",
        "photo": "jpg",
        "document": "pdf",
        "audio": "mp3"
    }.get(file_type, "bin")
    
    return f"downloaded_file_{int(time.time())}.{extension}"


async def is_private_chat(event):
    return event.is_private


async def save_user_data(user_id, key, value):
    await users_collection.update_one(
        {"user_id": user_id},
        {"$set": {key: value}},
        upsert=True
    )
   # print(users_collection)


async def get_user_data_key(user_id, key, default=None):
    user_data = await users_collection.find_one({"user_id": int(user_id)})
  #  print(f"Fetching key '{key}' for user {user_id}: {user_data}")
    return user_data.get(key, default) if user_data else default


async def get_user_data(user_id):
    try:
        user_data = await users_collection.find_one({"user_id": user_id})
        return user_data
    except Exception as e:
   #     logger.error(f"Error retrieving user data for {user_id}: {e}")
        return None


async def save_user_session(user_id, session_string):
    try:
        await users_collection.update_one(
            {"user_id": user_id},
            {"$set": {
                "session_string": session_string,
                "updated_at": datetime.now()
            }},
            upsert=True
        )
        logger.info(f"Saved session for user {user_id}")
        return True
    except Exception as e:
        logger.error(f"Error saving session for user {user_id}: {e}")
        return False


async def remove_user_session(user_id):
    try:
        await users_collection.update_one(
            {"user_id": user_id},
            {"$unset": {"session_string": ""}}
        )
        logger.info(f"Removed session for user {user_id}")
        return True
    except Exception as e:
        logger.error(f"Error removing session for user {user_id}: {e}")
        return False


async def save_user_bot(user_id, bot_token):
    try:
        await users_collection.update_one(
            {"user_id": user_id},
            {"$set": {
                "bot_token": bot_token,
                "updated_at": datetime.now()
            }},
            upsert=True
        )
        logger.info(f"Saved bot token for user {user_id}")
        return True
    except Exception as e:
        logger.error(f"Error saving bot token for user {user_id}: {e}")
        return False


async def remove_user_bot(user_id):
    try:
        await users_collection.update_one(
            {"user_id": user_id},
            {"$unset": {"bot_token": ""}}
        )
        logger.info(f"Removed bot token for user {user_id}")
        return True
    except Exception as e:
        logger.error(f"Error removing bot token for user {user_id}: {e}")
        return False


async def process_text_with_rules(user_id, text):
    if not text:
        return ""
    
    try:
        replacements = await get_user_data_key(user_id, "replacement_words", {})
        delete_words = await get_user_data_key(user_id, "delete_words", [])
        
        processed_text = text
        for word, replacement in replacements.items():
            processed_text = processed_text.replace(word, replacement)
        
        if delete_words:
            words = processed_text.split()
            filtered_words = [w for w in words if w not in delete_words]
            processed_text = " ".join(filtered_words)
        
        return processed_text
    except Exception as e:
        logger.error(f"Error processing text with rules: {e}")
        return text


def _is_user_thumbnail_path(path: str, sender: str | int | None = None) -> bool:
    if not path:
        return False
    base = os.path.basename(path)
    if base == "settings.jpg":
        return True
    if sender is not None and base == f"{sender}.jpg":
        return True
    if re.fullmatch(r"\d+\.jpg", base):
        return True
    return False


def cleanup_temp_file(path: str | None, sender: str | int | None = None) -> None:
    if not path:
        return
    if _is_user_thumbnail_path(path, sender):
        return
    try:
        if os.path.exists(path):
            os.remove(path)
    except Exception:
        pass


def cleanup_temp_images(directory: str = ".", max_age_hours: int = 24) -> int:
    removed = 0
    cutoff = time.time() - (max_age_hours * 3600)
    try:
        for name in os.listdir(directory):
            if not name.lower().endswith(".jpg"):
                continue
            full = os.path.join(directory, name)
            if not os.path.isfile(full):
                continue
            if _is_user_thumbnail_path(full):
                continue
            try:
                mtime = os.path.getmtime(full)
            except Exception:
                continue
            if mtime < cutoff:
                try:
                    os.remove(full)
                    removed += 1
                except Exception:
                    pass
    except Exception:
        pass
    return removed


async def screenshot(video: str, duration: int, sender: str) -> str | None:
    existing_screenshot = f"{sender}.jpg"
    if os.path.exists(existing_screenshot):
        return existing_screenshot

    time_stamp = hhmmss(duration // 2)
    output_file = datetime.now().isoformat("_", "seconds") + ".jpg"

    cmd = [
        "ffmpeg",
        "-ss", time_stamp,
        "-i", video,
        "-frames:v", "1",
        output_file,
        "-y"
    ]

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    
    stdout, stderr = await process.communicate()

    if os.path.isfile(output_file):
        return output_file
    else:
        print(f"FFmpeg Error: {stderr.decode().strip()}")
        return None


async def get_video_metadata(file_path):
    default_values = {'width': 1, 'height': 1, 'duration': 1}
    loop = asyncio.get_event_loop()
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)
    
    try:
        def _extract_metadata():
            try:
                vcap = cv2.VideoCapture(file_path)
                if not vcap.isOpened():
                    return default_values

                width = round(vcap.get(cv2.CAP_PROP_FRAME_WIDTH))
                height = round(vcap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                fps = vcap.get(cv2.CAP_PROP_FPS)
                frame_count = vcap.get(cv2.CAP_PROP_FRAME_COUNT)

                if fps <= 0:
                    return default_values

                duration = round(frame_count / fps)
                if duration <= 0:
                    return default_values

                vcap.release()
                return {'width': width, 'height': height, 'duration': duration}
            except Exception as e:
                logger.error(f"Error in video_metadata: {e}")
                return default_values
        
        return await loop.run_in_executor(executor, _extract_metadata)
        
    except Exception as e:
        logger.error(f"Error in get_video_metadata: {e}")
        return default_values


async def add_premium_user(user_id, duration_value, duration_unit):
    try:
        now = datetime.now()
        expiry_date = None
        
        if duration_unit == "min":
            expiry_date = now + timedelta(minutes=duration_value)
        elif duration_unit == "hours":
            expiry_date = now + timedelta(hours=duration_value)
        elif duration_unit == "days":
            expiry_date = now + timedelta(days=duration_value)
        elif duration_unit == "weeks":
            expiry_date = now + timedelta(weeks=duration_value)
        elif duration_unit == "month":
            expiry_date = now + timedelta(days=30 * duration_value)
        elif duration_unit == "year":
            expiry_date = now + timedelta(days=365 * duration_value)
        elif duration_unit == "decades":
            expiry_date = now + timedelta(days=3650 * duration_value)
        else:
            return False, "Invalid duration unit"
            
        await premium_users_collection.update_one(
            {"user_id": user_id},
            {"$set": {
                "user_id": user_id,
                "subscription_start": now,
                "subscription_end": expiry_date,
                "expireAt": expiry_date
            }},
            upsert=True
        )
        
        await premium_users_collection.create_index("expireAt", expireAfterSeconds=0)
        
        return True, expiry_date
    except Exception as e:
        logger.error(f"Error adding premium user {user_id}: {e}")
        return False, str(e)


async def is_premium_user(user_id):
    try:
        user = await premium_users_collection.find_one({"user_id": user_id})
        if user and "subscription_end" in user:
            now = datetime.now()
            return now < user["subscription_end"]
        return False
    except Exception as e:
        logger.error(f"Error checking premium status for {user_id}: {e}")
        return False


async def get_premium_details(user_id):
    try:
        user = await premium_users_collection.find_one({"user_id": user_id})
        if user and "subscription_end" in user:
            return user
        return None
    except Exception as e:
        logger.error(f"Error getting premium details for {user_id}: {e}")
        return None

# ─────────────────────────────────────────────────────────────
# WARNING / BAN SYSTEM (DB-based)
# ─────────────────────────────────────────────────────────────

# New collections for warnings / bans
warnings_collection = db["warnings"]
banned_users_collection = db["banned_users"]

async def add_warning_db(user_id: int, reason: str | None = None) -> int:
    """
    Increment a user's warning count in the DB and store reason/timestamp.
    Returns the new warning count (int).
    """
    now = int(time.time())
    doc = await warnings_collection.find_one({"user_id": user_id})

    if doc:
        new_count = int(doc.get("count", 0)) + 1
        await warnings_collection.update_one(
            {"user_id": user_id},
            {
                "$set": {"count": new_count, "last_warning": now},
                "$push": {"reasons": {"at": now, "reason": reason}},
            },
        )
    else:
        new_count = 1
        await warnings_collection.update_one(
            {"user_id": user_id},
            {
                "$set": {
                    "user_id": user_id,
                    "count": new_count,
                    "last_warning": now,
                    "reasons": [{"at": now, "reason": reason}],
                }
            },
            upsert=True,
        )

    return new_count


async def get_warnings_db(user_id: int) -> int:
    doc = await warnings_collection.find_one({"user_id": user_id})
    return int(doc.get("count", 0)) if doc else 0


async def reset_warnings_db(user_id: int):
    await warnings_collection.delete_one({"user_id": user_id})


async def ban_user_db(user_id: int, reason: str | None = None, banned_by: int | None = None):
    """
    Mark user as banned in DB (global ban).
    """
    now = int(time.time())
    await banned_users_collection.update_one(
        {"user_id": user_id},
        {"$set": {"user_id": user_id, "banned_at": now, "reason": reason, "banned_by": banned_by}},
        upsert=True,
    )


async def unban_user_db(user_id: int):
    await banned_users_collection.delete_one({"user_id": user_id})


async def is_user_banned_db(user_id: int) -> bool:
    doc = await banned_users_collection.find_one({"user_id": user_id})
    return bool(doc)


# --- NEW COLLECTIONS ---
access_users_collection = db["access_users"]     # bot access expiry store
warnings_collection = db["warnings"]             # warnings store
referrals_collection = db["referrals"]           # optional, but we can keep in users too

# --- WARNINGS ---
async def add_warning_db(user_id: int, reason: str = "") -> int:
    """
    increments warnings count, returns new warnings count
    """
    now = datetime.now()
    doc = await warnings_collection.find_one({"user_id": user_id}) or {"user_id": user_id, "count": 0}
    new_count = int(doc.get("count", 0)) + 1
    await warnings_collection.update_one(
        {"user_id": user_id},
        {"$set": {"user_id": user_id, "count": new_count, "updated_at": now},
         "$push": {"logs": {"at": now, "reason": reason}}},  # logs optional
        upsert=True
    )
    return new_count

async def get_warnings_db(user_id: int) -> int:
    doc = await warnings_collection.find_one({"user_id": user_id})
    return int(doc.get("count", 0)) if doc else 0

