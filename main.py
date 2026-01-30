
import asyncio
from shared_client import start_client, app
import importlib
import os
import sys
from utils.func import cleanup_temp_images
from pyrogram.errors import FloodWait


async def reset_active_batches_on_start():
    # Stop all running/pending/ytdl tasks on restart and notify users.
    try:
        from plugins import batch as batch_mod
        from plugins import ytdl as ytdl_mod
    except Exception:
        return

    active_ids = list(batch_mod.ACTIVE_USERS.keys())
    pending_ids = list(batch_mod.Z.keys())
    ytdl_ids = list(ytdl_mod.ongoing_downloads.keys())
    notify_ids = set(active_ids) | set(pending_ids) | set(ytdl_ids)
    if not notify_ids:
        return

    # Mark cancel requested and clear runtime states
    for uid_str in active_ids:
        try:
            batch_mod.ACTIVE_USERS[str(uid_str)]["cancel_requested"] = True
        except Exception:
            pass

    try:
        await batch_mod.save_active_users_to_file()
    except Exception:
        pass

    batch_mod.Z.clear()
    batch_mod.P.clear()
    batch_mod.PROCESSED_KEYS.clear()
    batch_mod.USER_LOCKS.clear()

    try:
        ytdl_mod.ongoing_downloads.clear()
    except Exception:
        pass

    # Notify users with active/pending/ytdl tasks
    notify_text = "⚠️ Bot restarted. Your task has been reset. Please retry."
    for uid_str in notify_ids:
        try:
            await app.send_message(int(uid_str), notify_text)
        except FloodWait as e:
            await asyncio.sleep(e.value)
            try:
                await app.send_message(int(uid_str), notify_text)
            except Exception:
                pass
        except Exception:
            pass

    try:
        batch_mod.ACTIVE_USERS.clear()
        await batch_mod.save_active_users_to_file()
    except Exception:
        pass

async def cleanup_loop(interval_seconds: int = 3600, max_age_hours: int = 24):
    while True:
        try:
            cleanup_temp_images(directory=".", max_age_hours=max_age_hours)
        except Exception:
            pass
        await asyncio.sleep(interval_seconds)

async def load_and_run_plugins():
    await start_client()
    await reset_active_batches_on_start()
    asyncio.create_task(cleanup_loop())
    plugin_dir = "plugins"
    plugins = [f[:-3] for f in os.listdir(plugin_dir) if f.endswith(".py") and f != "__init__.py"]

    for plugin in plugins:
        module = importlib.import_module(f"plugins.{plugin}")
        if hasattr(module, f"run_{plugin}_plugin"):
            print(f"Running {plugin} plugin...")
            await getattr(module, f"run_{plugin}_plugin")()  

async def main():
    await load_and_run_plugins()
    while True:
        await asyncio.sleep(1)  

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    print("Starting clients ...")
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        print("Shutting down...")
    except Exception as e:
        print(e)
        sys.exit(1)
    finally:
        try:
            loop.close()
        except Exception:
            pass
