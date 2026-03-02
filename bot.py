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

def load_schedule(): return load_json(SCHEDULE_FILE, {})
def save_schedule(schedule): save_json(SCHEDULE_FILE, schedule)
def load_next_schedule(): return load_json(NEXT_SCHEDULE_FILE, {})
def save_next_schedule(schedule): save_json(NEXT_SCHEDULE_FILE, schedule)
def load_mixes(): return load_json(MIXES_FILE, [])
def save_mixes(mixes): save_json(MIXES_FILE, mixes)

# === Перевірка адміна ===
def is_admin(update: Update) -> bool:
    return update.effective_user and update.effective_user.id == ADMIN_ID

# === Кнопки ===
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

# === Повідомлення ===
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

def empty_schedule_template():
    return {cafe: {day: "" for day in DAYS.values()} for cafe in GROUP_TOPICS.keys()}

# === START ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == ADMIN_ID:
        await update.message.reply_text(
            "Привіт! Використовуй кнопки нижче:",
            reply_markup=get_main_keyboard()
        )
    else:
        await update.message.reply_text(
            "Привіт! Це бот графіку. Меню доступне лише адміну."
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
        await query.edit_message_text("Привіт! Використовуй кнопки нижче:", reply_markup=get_main_keyboard())
        return

    elif data == "show":
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
        # Створюємо порожній шаблон і зберігаємо у next_schedule.json
        next_schedule = empty_schedule_template()
        save_next_schedule(next_schedule)
        template_text = "🆕 Створено новий графік на наступний тиждень.\n\n" \
                        "Відредагуй його у Telegram у форматі:\n" \
                        "`/uploadnext Cafe Day Person`\n" \
                        "Наприклад:\n" \
                        "`/uploadnext DailyDose1 Mon Олена`\n\n" \
                        "Поки графік порожній, він збережений у next_schedule.json."
        await query.edit_message_text(template_text, reply_markup=get_back_keyboard())

    elif data == "activate_now":
        next_schedule = load_next_schedule()
        if not next_schedule:
            await query.edit_message_text("❌ Нового графіку немає!", reply_markup=get_back_keyboard())
            return
        save_schedule(next_schedule)
        save_next_schedule({})
        await query.edit_message_text("✅ Новий графік активовано!", reply_markup=get_back_keyboard())

    elif data == "update":
        await query.edit_message_text(
            "Формат:\n/update Cafe Day Person\nПриклад:\n/update DailyDose1 Wed Олена",
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
            "Формат:\n/update Cafe Day Person\nПриклад:\n/update DailyDose1 Wed Олена"
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

# === /uploadnext для додавання нового графіку ===
async def upload_next(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    if len(context.args) < 3:
        await update.message.reply_text(
            "Формат:\n/uploadnext Cafe Day Person\nПриклад:\n/uploadnext DailyDose1 Mon Олена"
        )
        return
    cafe, day_short, person = context.args[0], context.args[1], " ".join(context.args[2:])
    if cafe not in GROUP_TOPICS:
        await update.message.reply_text("Такого закладу немає")
        return
    if day_short not in DAYS:
        await update.message.reply_text("Використовуй: Mon Tue Wed Thu Fri Sat Sun")
        return
    next_schedule = load_next_schedule()
    if cafe not in next_schedule:
        next_schedule[cafe] = {}
    next_schedule[cafe][DAYS[day_short]] = person
    save_next_schedule(next_schedule)
    await update.message.reply_text(f"✅ {cafe} {DAYS[day_short]} оновлено у next_schedule.json")

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
    now = datetime.now(KYIV_TZ)
    if now.weekday() != 6 or now.hour != 22:
        return
    next_schedule = load_next_schedule()
    if not any(person.strip() for cafe in next_schedule.values() for person in cafe.values()):
        return
    save_schedule(next_schedule)
    save_next_schedule({})
    print("✅ Автоматично активовано новий графік о 22:00")

# === ЗАПУСК ===
def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("update", update_shift))
    app.add_handler(CommandHandler("addmix", add_mix))
    app.add_handler(CommandHandler("uploadnext", upload_next))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.ChatType.PRIVATE, handle_mix))
    app.add_handler(CallbackQueryHandler(button_callback))

    # Щоденна розсилка о 12:00
    app.job_queue.run_daily(send_daily, time(hour=12, minute=0, tzinfo=KYIV_TZ))

    # Автоактивація нового графіку неділя о 22:00
    app.job_queue.run_daily(auto_activate_next_schedule, time(hour=22, minute=0, tzinfo=KYIV_TZ))

    print("🤖 Bot started")
    app.run_polling()

if __name__ == "__main__":
    main()