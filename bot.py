import json
import os
import random
from datetime import datetime, time
from pytz import timezone

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
    CallbackQueryHandler,
)

# === Налаштування ===
TOKEN = os.getenv("TOKEN").strip()
ADMIN_ID = 662089451

SCHEDULE_FILE = "schedule.json"
NEXT_SCHEDULE_FILE = "next_schedule.json"
MIXES_FILE = "mixes.json"

KYIV_TZ = timezone("Europe/Kyiv")

GROUP_TOPICS = {
    "DailyDose1": {"chat_id": -1002299751427, "topic_id": 225},
    "DailyDose2": {"chat_id": -1002299751427, "topic_id": 230},
    "DailyDose3": {"chat_id": -1002299751427, "topic_id": 227},
    "Citadell": {"chat_id": -1002299751427, "topic_id": 901},
    "Rafael": {"chat_id": -1002299751427, "topic_id": 2389},
}

DAYS = {
    "Mon": "Monday",
    "Tue": "Tuesday",
    "Wed": "Wednesday",
    "Thu": "Thursday",
    "Fri": "Friday",
    "Sat": "Saturday",
    "Sun": "Sunday",
}

# === Перевірка адміна ===
def is_admin(update: Update) -> bool:
    return update.effective_user and update.effective_user.id == ADMIN_ID

# === Робота з файлами ===
def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_json(path, default):
    if not os.path.exists(path):
        save_json(path, default)
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def load_schedule():
    return load_json(SCHEDULE_FILE, {})

def save_schedule(schedule):
    save_json(SCHEDULE_FILE, schedule)

def load_next_schedule():
    return load_json(NEXT_SCHEDULE_FILE, {})

def save_next_schedule(schedule):
    save_json(NEXT_SCHEDULE_FILE, schedule)

def load_mixes():
    return load_json(MIXES_FILE, [])

def save_mixes(mixes):
    save_json(MIXES_FILE, mixes)

# === Повідомлення на сьогодні ===
def get_today_message(schedule, cafe=None):
    today = datetime.now(KYIV_TZ).strftime("%A")

    if cafe:
        person = schedule.get(cafe, {}).get(today, "Ніхто не запланований")
        return f"📅 Сьогодні на зміні: {person}"

    msg = "📅 Сьогодні на зміні:\n\n"
    for c in GROUP_TOPICS.keys():
        person = schedule.get(c, {}).get(today, "Ніхто не запланований")
        msg += f"{c}: {person}\n"

    return msg

# === Макет порожнього графіку ===
def empty_schedule_template():
    return {
        cafe: {day: "" for day in DAYS.values()} for cafe in GROUP_TOPICS.keys()
    }

# === АВТОМАТИЧНА АКТИВАЦІЯ НОВОГО ГРАФІКУ ===
async def auto_activate_next_schedule(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now(KYIV_TZ)
    print(f"🕒 Перевірка автоактивації: {now}")

    # Monday=0 ... Sunday=6
    if now.weekday() != 6:
        print("⛔ Не неділя — пропускаємо")
        return

    if now.hour != 22:
        print("⛔ Не 22:00 — пропускаємо")
        return

    next_schedule = load_next_schedule()

    has_data = any(
        person.strip()
        for cafe in next_schedule.values()
        for person in cafe.values()
    )

    if not has_data:
        print("⚠️ Новий графік порожній — активацію скасовано")
        return

    save_schedule(next_schedule)
    save_next_schedule({})

    print("✅ Новий графік успішно активовано о 22:00")

# === ЩОДЕННА РОЗСИЛКА ===
async def send_daily(context: ContextTypes.DEFAULT_TYPE):
    schedule = load_schedule()
    for cafe, ids in GROUP_TOPICS.items():
        msg = get_today_message(schedule, cafe)
        await context.bot.send_message(
            chat_id=ids["chat_id"],
            message_thread_id=ids["topic_id"],
            text=msg,
        )

# === ЗАПУСК ===
def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("update", lambda u, c: None))
    app.add_handler(CommandHandler("addmix", lambda u, c: None))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.ChatType.PRIVATE, lambda u, c: None))

    # Щоденна розсилка о 12:00
    app.job_queue.run_daily(
        send_daily,
        time(hour=12, minute=0, tzinfo=KYIV_TZ)
    )

    # Перевірка кожної неділі о 22:00
    app.job_queue.run_daily(
        auto_activate_next_schedule,
        time(hour=22, minute=0, tzinfo=KYIV_TZ),
        days=(0,)  # 0 = Sunday у PTB v20+
    )

    print("🤖 Bot started")
    app.run_polling()

if __name__ == "__main__":
    main()