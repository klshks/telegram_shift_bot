import json
import os
import re
from datetime import datetime, time

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
TOKEN = "8482451594:AAEhmluDZfwyZaK0m6n49ln-8txdJgKgSc4"
ADMIN_ID = 662089451
SCHEDULE_FILE = "schedule.json"

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


# === Робота з файлом ===
def save_schedule(schedule):
    with open(SCHEDULE_FILE, "w", encoding="utf-8") as f:
        json.dump(schedule, f, ensure_ascii=False, indent=2)


def load_schedule():
    if not os.path.exists(SCHEDULE_FILE):
        save_schedule({})
        return {}
    with open(SCHEDULE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


# === Парсинг графіку ===
def parse_text_schedule(text: str):
    schedule = {}
    current_cafe = None

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue

        if line.endswith(":"):
            current_cafe = line[:-1]
            schedule[current_cafe] = {}
            continue

        if current_cafe:
            m = re.match(r"(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s*[:\-]\s*(.+)", line)
            if m:
                day_short, name = m.groups()
                schedule[current_cafe][DAYS[day_short]] = name.strip()

    return schedule


# === Повідомлення на сьогодні ===
def get_today_message(schedule, cafe=None):
    today = datetime.today().strftime("%A")
    if cafe:
        person = schedule.get(cafe, {}).get(today, "Ніхто не запланований")
        return f"📅 Сьогодні на зміні: {person}"

    msg = "📅 Сьогодні на зміні:\n\n"
    for c in GROUP_TOPICS.keys():
        person = schedule.get(c, {}).get(today, "Ніхто не запланований")
        msg += f"{c}: {person}\n"
    return msg


# === КОМАНДА START + меню кнопок ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return

    keyboard = [
        [InlineKeyboardButton("📅 Показати сьогодні", callback_data="show")],
        [InlineKeyboardButton("🔄 Змінити зміну", callback_data="update")],
        [InlineKeyboardButton("📝 Макет графіку", callback_data="template")],
        [InlineKeyboardButton("📨 Тестова розсилка", callback_data="testsend")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.effective_chat.type != "private":
        await context.bot.send_message(
            chat_id=update.effective_user.id,
            text="Привіт! Використовуй меню нижче:",
            reply_markup=reply_markup,
        )
        return

    await update.message.reply_text(
        "Привіт! Використовуй кнопки нижче для роботи з графіком:",
        reply_markup=reply_markup,
    )


# === Обробка натискання кнопок ===
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_admin(update):
        return

    data = query.data
    if data == "show":
        schedule = load_schedule()
        await query.edit_message_text(get_today_message(schedule))
    elif data == "update":
        await query.edit_message_text(
            "Щоб змінити зміну, використай команду:\n/update Cafe Day Person\n"
            "Приклад:\n/update DailyDose1 Wed Олена"
        )
    elif data == "template":
        # Надсилаємо пустий макет
        template = "\n".join([f"{c}:\nMon: \nTue: \nWed: \nThu: \nFri: \nSat: \nSun:" for c in GROUP_TOPICS.keys()])
        await query.edit_message_text(f"Макет для заповнення:\n\n{template}")
    elif data == "testsend":
        await send_daily(context)
        await query.edit_message_text("Тестова розсилка надіслана ✅")


# === Текстові команди ===
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update) or update.effective_chat.type != "private":
        return

    schedule = parse_text_schedule(update.message.text)
    if schedule:
        save_schedule(schedule)
        await update.message.reply_text("Графік збережено ✅")
    else:
        await update.message.reply_text("❌ Не вдалося розпізнати графік")


async def update_shift(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    if len(context.args) < 3:
        await update.message.reply_text(
            "Формат:\n/update Cafe Day Person\n"
            "Приклад:\n/update DailyDose1 Wed Олена"
        )
        return

    cafe, day_short, person = context.args[0], context.args[1], " ".join(context.args[2:])
    if day_short not in DAYS:
        await update.message.reply_text("Використовуй: Mon Tue Wed Thu Fri Sat Sun")
        return

    schedule = load_schedule()
    if cafe not in schedule:
        await update.message.reply_text("Такого закладу нема")
        return

    schedule[cafe][DAYS[day_short]] = person
    save_schedule(schedule)
    await update.message.reply_text(f"Зміна оновлена ✅ {cafe} {DAYS[day_short]}: {person}")


# === Щоденна розсилка ===
async def send_daily(context: ContextTypes.DEFAULT_TYPE):
    schedule = load_schedule()
    for cafe, ids in GROUP_TOPICS.items():
        msg = get_today_message(schedule, cafe)
        await context.bot.send_message(
            chat_id=ids["chat_id"],
            message_thread_id=ids["topic_id"],
            text=msg,
        )


# === Запуск бота ===
def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("update", update_shift))
    app.add_handler(MessageHandler(filters.TEXT & filters.ChatType.PRIVATE, handle_text))
    app.add_handler(CallbackQueryHandler(button_callback))

    # Автопост о 12:00
    app.job_queue.run_daily(send_daily, time(hour=12, minute=0))

    print("🤖 Bot started")
    app.run_polling()


if __name__ == "__main__":
    main()