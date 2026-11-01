import re
import asyncio
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
from pyrogram import Client, filters
from pyrogram.types import Message

# ---- Scheduler setup ----
scheduler = AsyncIOScheduler()
scheduler.start()

# In-memory store: {job_id: job}
# (Production me DB use karo — SQLite/MongoDB)
PENDING = {}
_job_counter = 0


def next_id():
    global _job_counter
    _job_counter += 1
    return _job_counter


def parse_datetime(date_str: str, time_str: str) -> datetime:
    """date: DD-MM-YYYY or YYYY-MM-DD, time: HH:MM (24h)."""
    for fmt in ("%d-%m-%Y %H:%M", "%Y-%m-%d %H:%M", "%d/%m/%Y %H:%M"):
        try:
            return datetime.strptime(f"{date_str} {time_str}", fmt)
        except ValueError:
            continue
    raise ValueError("Invalid date/time. Use: DD-MM-YYYY HH:MM")


def parse_target(client: Client, target: str):
    """target: @username | me | -100xxxx | https://t.me/..."""
    target = target.strip()
    if target.lower() == "me":
        return "me"
    if target.startswith("@"):
        return target
    if target.lstrip("-").isdigit():
        return int(target)
    m = re.match(r"https?://t\.me/([\w_]+)", target)
    if m:
        return m.group(1)
    return target


async def _send_job(client: Client, job_id: int, target, msg: str):
    try:
        await client.send_message(target, msg)
    except Exception as e:
        print(f"[scheduler] job {job_id} failed: {e}")
    finally:
        PENDING.pop(job_id, None)


# ---------- .schedule ----------
@Client.on_message(filters.me & filters.regex(r"^\.schedule\s+"))
async def cmd_schedule(client: Client, message: Message):
    parts = message.text.split(maxsplit=4)
    if len(parts) < 5:
        return await message.edit_text(
            "**Usage:** `.schedule <date> <time> <target> <msg>`\n"
            "Example: `.schedule 25-12-2025 18:30 @mychannel Happy Diwali!`"
        )

    _, date_s, time_s, target_s, msg = parts
    try:
        run_at = parse_datetime(date_s, time_s)
    except ValueError as e:
        return await message.edit_text(f"❌ {e}")

    if run_at <= datetime.now():
        return await message.edit_text("❌ Time is in the past.")

    target = parse_target(client, target_s)
    job_id = next_id()

    job = scheduler.add_job(
        _send_job,
        trigger=DateTrigger(run_date=run_at),
        args=[client, job_id, target, msg],
        id=str(job_id),
    )
    PENDING[job_id] = {
        "type": "schedule",
        "target": str(target),
        "msg": msg,
        "run_at": run_at,
        "job": job,
    }

    await message.edit_text(
        f"✅ **Scheduled** (ID: `{job_id}`)\n"
        f"🕒 {run_at:%d-%m-%Y %H:%M}\n"
        f"🎯 `{target}`\n"
        f"💬 {msg[:60]}"
    )


# ---------- .schedulech ----------
@Client.on_message(filters.me & filters.regex(r"^\.schedulech\s+"))
async def cmd_schedulech(client: Client, message: Message):
    parts = message.text.split(maxsplit=4)
    if len(parts) < 5:
        return await message.edit_text(
            "**Usage:** `.schedulech <date> <time> <post_link> <msg>`\n"
            "Example: `.schedulech 25-12-2025 18:30 https://t.me/mychannel/45 Check this!`"
        )

    _, date_s, time_s, link, msg = parts
    try:
        run_at = parse_datetime(date_s, time_s)
    except ValueError as e:
        return await message.edit_text(f"❌ {e}")

    if run_at <= datetime.now():
        return await message.edit_text("❌ Time is in the past.")

    m = re.match(r"https?://t\.me/(?:c/)?([\w_]+)/(\d+)", link)
    if not m:
        return await message.edit_text("❌ Invalid post link. Format: `https://t.me/channel/123`")

    chat, post_id = m.group(1), int(m.group(2))
    job_id = next_id()

    async def _reply_job():
        try:
            await client.send_message(chat, msg, reply_to_message_id=post_id)
        except Exception as e:
            print(f"[schedulech] job {job_id} failed: {e}")
        finally:
            PENDING.pop(job_id, None)

    job = scheduler.add_job(
        _reply_job,
        trigger=DateTrigger(run_date=run_at),
        id=str(job_id),
    )
    PENDING[job_id] = {
        "type": "schedulech",
        "target": f"{chat}/{post_id}",
        "msg": msg,
        "run_at": run_at,
        "job": job,
    }

    await message.edit_text(
        f"✅ **Scheduled reply** (ID: `{job_id}`)\n"
        f"🕒 {run_at:%d-%m-%Y %H:%M}\n"
        f"🔗 `{chat}/{post_id}`\n"
        f"💬 {msg[:60]}"
    )


# ---------- .schedules ----------
@Client.on_message(filters.me & filters.regex(r"^\.schedules$"))
async def cmd_schedules(client: Client, message: Message):
    if not PENDING:
        return await message.edit_text("📭 No pending schedules.")

    lines = ["**⏰ Pending schedules**\n"]
    for jid, info in sorted(PENDING.items(), key=lambda x: x[1]["run_at"]):
        lines.append(
            f"`#{jid}` • {info['run_at']:%d-%m-%Y %H:%M}\n"
            f"   ▸ {info['type']} → `{info['target']}`\n"
            f"   ▸ {info['msg'][:50]}\n"
        )
    await message.edit_text("\n".join(lines))


# ---------- .cancelschedule ----------
@Client.on_message(filters.me & filters.regex(r"^\.cancelschedule\s+(\d+)$"))
async def cmd_cancel(client: Client, message: Message):
    jid = int(message.matches[0].group(1))
    info = PENDING.pop(jid, None)
    if not info:
        return await message.edit_text(f"❌ No schedule with ID `{jid}`.")

    try:
        scheduler.remove_job(str(jid))
    except Exception:
        pass

    await message.edit_text(f"🗑️ Cancelled schedule `#{jid}`.")
