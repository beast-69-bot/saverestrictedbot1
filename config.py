

import os
from dotenv import load_dotenv

dotenv_path = os.getenv("DOTENV_PATH")
if dotenv_path:
    load_dotenv(dotenv_path)
else:
    load_dotenv()

# ════════════════════════════════════════════════════════════════════════════════
# ░ CONFIGURATION SETTINGS
# ════════════════════════════════════════════════════════════════════════════════
MIN_VERIFY_DELAY = int(float(os.environ.get("MIN_VERIFY_DELAY", 60)))  # seconds

# VPS --- FILL COOKIES 🍪 in """ ... """ 
INST_COOKIES = """
# write up here insta cookies
"""

YTUB_COOKIES = """
# write here yt cookies
"""

# ─── BOT / DATABASE CONFIG ──────────────────────────────────────────────────────
API_ID       = os.getenv("API_ID", "")
API_HASH     = os.getenv("API_HASH", "")
BOT_TOKEN    = os.getenv("BOT_TOKEN", "")
MONGO_DB     = os.getenv("MONGO_DB", "")
DB_NAME      = os.getenv("DB_NAME", "telegram_downloader")

# SESSION NAMES (for multi-bot on same host)
TELETHON_SESSION = os.getenv("TELETHON_SESSION", "telethonbot")
PYRO_SESSION     = os.getenv("PYRO_SESSION", "pyrogrambot")
USERBOT_SESSION  = os.getenv("USERBOT_SESSION", "4gbbot")

# ─── OWNER / CONTROL SETTINGS ───────────────────────────────────────────────────
OWNER_ID     = list(map(int, os.getenv("OWNER_ID", "8185612154").split()))  # space-separated list
STRING       = os.getenv("STRING", None)  # optional session string
LOG_GROUP    = int(os.getenv("LOG_GROUP", "-1005228054904"))
FORCE_SUB    = int(os.getenv("FORCE_SUB", "-1003571680513"))

# ─── SECURITY KEYS ──────────────────────────────────────────────────────────────
MASTER_KEY   = os.getenv("MASTER_KEY", "gK8HzLfT9QpViJcYeB5wRa3DmN7P2xUq")  # session encryption
IV_KEY       = os.getenv("IV_KEY", "s7Yx5CpVmE3F")  # decryption key

# ─── COOKIES HANDLING ───────────────────────────────────────────────────────────
YT_COOKIES   = os.getenv("YT_COOKIES", YTUB_COOKIES)
INSTA_COOKIES = os.getenv("INSTA_COOKIES", INST_COOKIES)

# ─── USAGE LIMITS ───────────────────────────────────────────────────────────────
FREEMIUM_LIMIT = int(os.getenv("FREEMIUM_LIMIT", "69"))
PREMIUM_LIMIT  = int(os.getenv("PREMIUM_LIMIT", "500000"))
FREE_BATCH_DAILY_LIMIT = int(os.getenv("FREE_BATCH_DAILY_LIMIT", "5"))

# --- SHORTLINK / VERIFY CONFIG ---
SHORTLINK_SITE = os.getenv("SHORTLINK_SITE", "caslinks.com")
SHORTLINK_API = os.getenv("SHORTLINK_API", "05b01394bd9824e3f76ff2191417922006c97dbf")
VERIFY_PHOTO = os.getenv("VERIFY_PHOTO", "https://files.catbox.moe/uld6uo.jpg")
VERIFY_TUTORIAL = os.getenv("VERIFY_TUTORIAL", "https://t.me/aztutorial12321/32")
VERIFY_EXPIRE = int(float(os.getenv("VERIFY_EXPIRE", 86400)))
TOKEN_TTL = int(float(os.getenv("TOKEN_TTL", 300)))
MIN_TOKEN_AGE = int(float(os.getenv("MIN_TOKEN_AGE", 60)))

# ─── UI / LINKS ─────────────────────────────────────────────────────────────────
JOIN_LINK     = os.getenv("JOIN_LINK", "https://t.me/az_bots_solution")
ADMIN_CONTACT = os.getenv("ADMIN_CONTACT", "https://t.me/eurnyme")

# ════════════════════════════════════════════════════════════════════════════════
# ░ PREMIUM PLANS CONFIGURATION
# ════════════════════════════════════════════════════════════════════════════════

P0 = {
    "d": {
        "s": int(os.getenv("PLAN_D_S", 1)),
        "du": int(os.getenv("PLAN_D_DU", 1)),
        "u": os.getenv("PLAN_D_U", "days"),
        "l": os.getenv("PLAN_D_L", "Daily"),
    },
    "w": {
        "s": int(os.getenv("PLAN_W_S", 3)),
        "du": int(os.getenv("PLAN_W_DU", 1)),
        "u": os.getenv("PLAN_W_U", "weeks"),
        "l": os.getenv("PLAN_W_L", "Weekly"),
    },
    "m": {
        "s": int(os.getenv("PLAN_M_S", 5)),
        "du": int(os.getenv("PLAN_M_DU", 1)),
        "u": os.getenv("PLAN_M_U", "month"),
        "l": os.getenv("PLAN_M_L", "Monthly"),
    },
}

# ════════════════════════════════════════════════════════════════════════════════
# ░ az bots solution - 2024
# ════════════════════════════════════════════════════════════════════════════════




