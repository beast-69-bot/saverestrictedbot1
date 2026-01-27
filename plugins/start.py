from datetime import datetime
from shared_client import app
from pyrogram import filters
from pyrogram.errors import UserNotParticipant
from pyrogram.types import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup
from config import LOG_GROUP, OWNER_ID, FORCE_SUB

from utils.func import is_user_banned_db, save_user_data
from utils.func import users_collection, add_premium_user

async def subscribe(client, message):
    # ✅ Track user in DB (so /get shows everyone who used bot)
    try:
        if message.from_user:
            await save_user_data(message.from_user.id, "last_seen", datetime.now())
    except Exception:
        pass

    # ✅ DB ban check first
    try:
        uid = message.from_user.id
        if await is_user_banned_db(uid):
            cfg = __import__("config")
            contact = getattr(cfg, "ADMIN_CONTACT", "")
            await message.reply_text(f"⛔ You are banned.\nContact admins: {contact}")
            return 1
    except Exception:
        pass

    # ✅ Force sub check
    if FORCE_SUB:
        try:
            user = await client.get_chat_member(FORCE_SUB, message.from_user.id)
            if str(user.status) == "ChatMemberStatus.BANNED":
                await message.reply_text("⛔ You are banned in our channel. Contact admin.")
                return 1

        except UserNotParticipant:
            link = await client.export_chat_invite_link(FORCE_SUB)
            caption = "Join our channel to use the bot"
            await message.reply_photo(
                photo="https://files.catbox.moe/75fctj.jpg",
                caption=caption,
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("Join Now...", url=link)]]
                )
            )
            return 1

        except Exception as ggn:
            await message.reply_text(f"Something went wrong. Contact admins...\n\nError: {ggn}")
            return 1
    

@app.on_message(filters.command("set"))
async def set(_, message):
    if message.from_user.id not in OWNER_ID:
        await message.reply_text("⛔ You are not authorized to use this command.")
        return

    await app.set_bot_commands([
        BotCommand("start", "🚀 Start"),
        BotCommand("help", "📖 How to use"),
        BotCommand("login", "🔐 Login (private chats)"),
        BotCommand("logout", "🚪 Logout"),
        BotCommand("setbot", "🤖 Add your bot token"),
        BotCommand("rembot", "🧹 Remove your bot token"),
        BotCommand("single", "🎯 Extract single post"),
        BotCommand("batch", "📦 Extract in bulk"),
        BotCommand("stop", "🛑 Stop active batch"),
        BotCommand("cancel", "❌ Cancel current step"),
        BotCommand("settings", "⚙️ Customize caption/rename/thumb"),
        BotCommand("status", "📌 My status / plan"),
        BotCommand("plan", "💎 Premium plans"),
        BotCommand("terms", "📜 Terms"),
        BotCommand("transfer", "🎁 Transfer premium"),
        BotCommand("add", "➕ Add premium (Owner)"),
        BotCommand("rem", "➖ Remove premium (Owner)"),
        BotCommand("broadcast", "📣 Broadcast (Owner)"),
        BotCommand("tokenon", "✅ Enable token verification (Owner)"),
        BotCommand("tokenoff", "❌ Disable token verification (Owner)"),
        BotCommand("tokenstatus", "ℹ️ Token verification status (Owner)")
    ])

    await message.reply_text("✅ Bot commands updated successfully!")


help_pages = [
    (
        "📖 **Help (1/2)**\n\n"
        "✅ **Basic Commands**\n"
        "• **/start** - Start the bot\n"
        "• **/help** - See this help\n"
        "• **/status** - Check your login & premium status\n\n"
        "🔐 **Login (for private channels/groups)**\n"
        "• **/login** - Login using phone\n"
        "• **/logout** - Logout safely\n\n"
        "📥 **Extraction**\n"
        "• **/single** - Extract 1 post link\n"
        "• **/batch** - Extract multiple posts\n"
        "• **/stop** - Stop running batch safely\n\n"
        "⚙️ **Customization**\n"
        "• **/settings** - Caption / rename / thumbnail etc.\n"
        "• **/setbot** - Add your bot token (required)\n"
        "• **/rembot** - Remove your bot token\n"
    ),
    (
        "📖 **Help (2/2)**\n\n"
        "💎 **Premium**\n"
        "• **/plan** - View premium plans\n"
        "• **/transfer user_id** - Transfer premium to another user\n\n"
        "👑 **Owner Commands**\n"
        "• **/add user_id value unit** - Add premium (ex: `/add 123 1 week`)\n"
        "• **/rem user_id** - Remove premium\n"
        "• **/broadcast** - Send message to all users\n"
        "• **/tokenon** - Enable token verification\n"
        "• **/tokenoff** - Disable token verification\n"
        "• **/tokenstatus** - Token verification status\n\n"
        "📜 **Legal**\n"
        "• **/terms** - Terms & Conditions\n\n"
        "**__Powered by AZ BOTS ADDA__**"
    )
]
async def send_or_edit_help_page(_, message, page_number):
    if page_number < 0 or page_number >= len(help_pages):
        return

    prev_button = InlineKeyboardButton("◀️ Previous", callback_data=f"help_prev_{page_number}")
    next_button = InlineKeyboardButton("Next ▶️", callback_data=f"help_next_{page_number}")

    buttons = []
    if page_number > 0:
        buttons.append(prev_button)
    if page_number < len(help_pages) - 1:
        buttons.append(next_button)

    keyboard = InlineKeyboardMarkup([buttons])

    try:
        await message.delete()
    except Exception:
        pass

    await message.reply(help_pages[page_number], reply_markup=keyboard)


@app.on_message(filters.command("help"))
async def help(client, message):
    join = await subscribe(client, message)
    if join == 1:
        return
    await send_or_edit_help_page(client, message, 0)


@app.on_callback_query(filters.regex(r"help_(prev|next)_(\d+)"))
async def on_help_navigation(client, callback_query):
    action, page_number = callback_query.data.split("_")[1], int(callback_query.data.split("_")[2])

    if action == "prev":
        page_number -= 1
    elif action == "next":
        page_number += 1

    await send_or_edit_help_page(client, callback_query.message, page_number)
    await callback_query.answer()


@app.on_message(filters.command("terms") & filters.private)
async def terms(client, message):
    join = await subscribe(client, message)
    if join == 1:
        return

    terms_text = (
    "📜 **Terms & Conditions** 📜\n\n"
    "• We do not promote piracy. Users are responsible for their own actions.\n"
    "• Service uptime, features, and access are not guaranteed and may change anytime.\n"
    "• Payment does not guarantee access to all commands (including **/batch**).\n"
    "• Misuse or abuse may result in restriction or permanent ban without refund.\n"
)


    buttons = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📋 See Plans", callback_data="see_plan")],
            [InlineKeyboardButton("💬 Contact Now", url="https://t.me/eurnyme")],
        ]
    )
    await message.reply_text(terms_text, reply_markup=buttons)


@app.on_message(filters.command("plan") & filters.private)
async def plan(client, message):
    join = await subscribe(client, message)
    if join == 1:
        return

    plan_text = (
    "💰 **Premium Plans** 💰\n\n"
    "⭐ **Premium Users**\n"
    "• No token verification required\n"
    "• Unlimited /batch access\n"
    "• Faster & priority processing\n\n"
    "🆓 **Free Users**\n"
    "• Daily **69 files** batch limit\n"
    "• Token verification required\n\n"
    "💳 **Pricing**\n"
    "• Starts from **$1 / ₹69** via **Amazon Gift Card**\n\n"
    "📜 For rules & details, use **/terms**"
)


    buttons = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📜 See Terms", callback_data="see_terms")],
            [InlineKeyboardButton("💬 Contact Now", url="https://t.me/Eurnyme")],
        ]
    )
    await message.reply_text(plan_text, reply_markup=buttons)


@app.on_callback_query(filters.regex("see_plan"))
async def see_plan(client, callback_query):
    plan_text = (
    "💰 **Premium Plans** 💰\n\n"
    "⭐ **Premium Users**\n"
    "• No token verification required\n"
    "• Unlimited /batch access\n"
    "• Faster & priority processing\n\n"
    "🆓 **Free Users**\n"
    "• Daily **69 files** batch limit\n"
    "• Token verification required\n\n"
    "💳 **Pricing**\n"
    "• Starts from **$1 / ₹69** via **Amazon Gift Card**\n\n"
    "📜 For rules & details, use **/terms**"
)


    buttons = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📜 See Terms", callback_data="see_terms")],
            [InlineKeyboardButton("💬 Contact Now", url="https://t.me/eurnyme")],
        ]
    )
    await callback_query.message.edit_text(plan_text, reply_markup=buttons)


@app.on_callback_query(filters.regex("see_terms"))
async def see_terms(client, callback_query):
    terms_text = (
    "📜 **Terms & Conditions** 📜\n\n"
    "• We do not promote piracy. Users are responsible for their own actions.\n"
    "• Service uptime, features, and access are not guaranteed and may change anytime.\n"
    "• Payment does not guarantee access to all commands (including **/batch**).\n"
    "• Misuse or abuse may result in restriction or permanent ban without refund.\n"
)


    buttons = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📋 See Plans", callback_data="see_plan")],
            [InlineKeyboardButton("💬 Contact Now", url="https://t.me/eurnyme")],
        ]
    )
    await callback_query.message.edit_text(terms_text, reply_markup=buttons)


