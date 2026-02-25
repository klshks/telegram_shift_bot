import json
import os
import re
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
    JobQueue,
)

# === Налаштування ===
TOKEN = os.getenv("TOKEN").strip()
ADMIN_ID = 662089451

SCHEDULE_FILE = "schedule.json"
NEXT_SCHEDULE_FILE = "next_schedule.json"
MIXES_FILE = "mixes.json"

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
    today = datetime.today().strftime("%A")

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

# === КНОПКИ ===
def get_main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📅 Показати сьогодні", callback_data="show")],
        [InlineKeyboardButton("🗓 Графік на тиждень", callback_data="show_week")],
        [InlineKeyboardButton("🆕 Новий графік на наступний тиждень", callback_data="new_next_week")],
        [InlineKeyboardButton("🔄 Змінити зміну", callback_data="update")],
        [InlineKeyboardButton("📝 Макет графіку", callback_data="template")],
        [InlineKeyboardButton("➕ Додати мікс", callback_data="addmix_btn")],
        [InlineKeyboardButton("📨 Тестова розсилка", callback_data="testsend")],
    ])

def get_back_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]
    ])

# === START ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return

    if update.effective_chat.type != "private":
        await context.bot.send_message(
            chat_id=update.effective_user.id,
            text="Привіт! Використовуй меню нижче:",
            reply_markup=get_main_keyboard()
        )
        return

    await update.message.reply_text(
        "Привіт! Використовуй кнопки нижче:",
        reply_markup=get_main_keyboard()
    )

# === CALLBACK BUTTONS ===
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_admin(update):
        return

    data = query.data
    schedule = load_schedule()

    if data == "back_to_main":
        await query.edit_message_text(
            "Привіт! Використовуй кнопки нижче:",
            reply_markup=get_main_keyboard()
        )
        return

    if data == "show":
        await query.edit_message_text(get_today_message(schedule), reply_markup=get_back_keyboard())

    elif data == "show_week":
        msg = "🗓 Графік на тиждень:\n\n"
        for cafe, shifts in schedule.items():
            msg += f"{cafe}:\n"
            for day, person in shifts.items():
                msg += f"{day}: {person}\n"
            msg += "\n"
        await query.edit_message_text(msg, reply_markup=get_back_keyboard())

    elif data == "new_next_week":
        next_schedule = empty_schedule_template()
        save_next_schedule(next_schedule)

        template_text = "🆕 Створено новий графік на наступний тиждень:\n\n"
        for cafe in next_schedule:
            template_text += f"{cafe}:\n"
            for day in next_schedule[cafe]:
                template_text += f"{day}: \n"
            template_text += "\n"

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔘 Активувати новий графік зараз", callback_data="activate_now")],
            [InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]
        ])
        await query.edit_message_text(template_text, reply_markup=keyboard)

    elif data == "activate_now":
        next_schedule = load_next_schedule()
        if not next_schedule:
            await query.edit_message_text("❌ Нового графіку немає!", reply_markup=get_back_keyboard())
            return
        save_schedule(next_schedule)
        await query.edit_message_text("✅ Новий графік активовано!", reply_markup=get_back_keyboard())

    elif data == "update":
        await query.edit_message_text(
            "Формат:\n/update Cafe Day Person\n"
            "Приклад:\n/update DailyDose1 Wed Олена",
            reply_markup=get_back_keyboard()
        )

    elif data == "template":
        template = "\n".join(
            [f"{c}:\nMon: \nTue: \nWed: \nThu: \nFri: \nSat: \nSun:" for c in GROUP_TOPICS.keys()]
        )
        await query.edit_message_text(f"Макет:\n\n{template}", reply_markup=get_back_keyboard())

    elif data == "addmix_btn":
        await query.edit_message_text("Відправ новий мікс командою:\n/addmix Текст міксу", reply_markup=get_back_keyboard())

    elif data == "testsend":
        await send_daily(context)
        await query.edit_message_text("Тестова розсилка надіслана ✅", reply_markup=get_back_keyboard())

# === ОНОВЛЕННЯ ЗМІНИ ===
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

# === ДОДАТИ МІКС ===
async def add_mix(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return

    if not context.args:
        await update.message.reply_text("Формат:\n/addmix Текст міксу")
        return

    mix_text = " ".join(context.args)
    mixes = load_mixes()
    mixes.append(mix_text)
    save_mixes(mixes)
    await update.message.reply_text("✅ Мікс додано")

# === РЕАКЦІЯ НА #mixforme ===
async def handle_mix(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    text = update.message.text.strip().lower()
    if text != "#mixforme":
        return

    chat_id = update.effective_chat.id
    topic_id = update.message.message_thread_id

    allowed = any(
        ids["chat_id"] == chat_id and ids["topic_id"] == topic_id
        for ids in GROUP_TOPICS.values()
    )

    if not allowed:
        return

    mixes = load_mixes()
    if not mixes:
        await update.message.reply_text("❌ База міксів порожня")
        return

    mix = random.choice(mixes)
    await update.message.reply_text(f"💨 Спробуй мікс:\n{mix}")

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

# === АВТОМАТИЧНА АКТИВАЦІЯ НОВОГО ГРАФІКУ ===
async def auto_activate_next_schedule(context: ContextTypes.DEFAULT_TYPE):
    next_schedule = load_next_schedule()
    if next_schedule:
        save_schedule(next_schedule)
        print("✅ Автоматично активовано новий графік")
    else:
        print("⚠️ Нового графіку немає, повторна спроба о 23:00")
        context.job_queue.run_once(auto_activate_next_schedule, when=time(hour=23, minute=0, tzinfo=timezone("Europe/Kyiv")))

# === ЗАПУСК ===
def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("update", update_shift))
    app.add_handler(CommandHandler("addmix", add_mix))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.ChatType.PRIVATE, handle_mix))
    app.add_handler(CallbackQueryHandler(button_callback))

    # Щоденна розсилка о 12:00
    app.job_queue.run_daily(
        send_daily,
        time(hour=12, minute=0, tzinfo=timezone("Europe/Kyiv"))
    )

    # Автоматична активація нового графіку неділя 22:00
    app.job_queue.run_daily(
        auto_activate_next_schedule,
        time(hour=22, minute=0, tzinfo=timezone("Europe/Kyiv")),
        days=(6,)  # 0=Mon, 6=Sun
    )

    print("🤖 Bot started")
    app.run_polling()

if __name__ == "__main__":
    main()