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
TOKEN = "8482451594:AAEhmluDZfwyZaK0m6n49ln-8txdJgKgSc4"
ADMIN_ID = 662089451

SCHEDULE_FILE = "schedule.json"
NEXT_SCHEDULE_FILE = "next_schedule.json"
MIXES_FILE = "mixes.json"

WAITING_FOR_NEXT_SCHEDULE = {}

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


# ==========================
# УТИЛІТИ
# ==========================

def is_admin(update: Update) -> bool:
    return update.effective_user and update.effective_user.id == ADMIN_ID


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_json(path, default):
    if not os.path.exists(path):
        save_json(path, default)
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def empty_schedule_template():
    return {
        cafe: {day: "" for day in DAYS.values()}
        for cafe in GROUP_TOPICS.keys()
    }


def load_schedule():
    return load_json(SCHEDULE_FILE, empty_schedule_template())


def save_schedule(schedule):
    save_json(SCHEDULE_FILE, schedule)


def load_next_schedule():
    return load_json(NEXT_SCHEDULE_FILE, empty_schedule_template())


def save_next_schedule(schedule):
    save_json(NEXT_SCHEDULE_FILE, schedule)


def load_mixes():
    return load_json(MIXES_FILE, [])


def save_mixes(mixes):
    save_json(MIXES_FILE, mixes)


def main_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton("📅 Показати сьогодні", callback_data="show")],
        [InlineKeyboardButton("🗓 Графік на тиждень", callback_data="show_week")],
        [InlineKeyboardButton("🆕 Новий графік на наступний тиждень", callback_data="new_next_week")],
        [InlineKeyboardButton("🚀 Активувати новий графік зараз", callback_data="activate_now")],
        [InlineKeyboardButton("🔄 Змінити зміну", callback_data="update")],
        [InlineKeyboardButton("📝 Макет графіку", callback_data="template")],
        [InlineKeyboardButton("➕ Додати мікс", callback_data="addmix_btn")],
        [InlineKeyboardButton("📨 Тестова розсилка", callback_data="testsend")],
    ]
    return InlineKeyboardMarkup(keyboard)


def back_keyboard():
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("⬅️ Назад", callback_data="back")]]
    )


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


# ==========================
# START
# ==========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return

    await context.bot.send_message(
        chat_id=update.effective_user.id,
        text="Головне меню:",
        reply_markup=main_menu_keyboard(),
    )


# ==========================
# CALLBACK КНОПКИ
# ==========================

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_admin(update):
        return

    data = query.data
    schedule = load_schedule()

    if data == "back":
        await query.edit_message_text("Головне меню:", reply_markup=main_menu_keyboard())

    elif data == "show":
        await query.edit_message_text(get_today_message(schedule), reply_markup=back_keyboard())

    elif data == "show_week":
        msg = "🗓 Графік на тиждень:\n\n"
        for cafe, shifts in schedule.items():
            msg += f"{cafe}:\n"
            for day, person in shifts.items():
                msg += f"{day}: {person}\n"
            msg += "\n"
        await query.edit_message_text(msg, reply_markup=back_keyboard())

    elif data == "activate_now":
        success = await transfer_schedule(context)
        if success:
            await query.edit_message_text("✅ Новий графік активовано", reply_markup=back_keyboard())
        else:
            await query.edit_message_text("⚠️ Новий графік порожній", reply_markup=back_keyboard())

    elif data == "new_next_week":
        template = empty_schedule_template()
        save_next_schedule(template)

        text = "🆕 Заповни цей графік і відправ його у відповідь:\n\n"
        for cafe in template:
            text += f"{cafe}:\n"
            for day in template[cafe]:
                text += f"{day}: \n"
            text += "\n"

        WAITING_FOR_NEXT_SCHEDULE[update.effective_user.id] = True
        await query.edit_message_text(text, reply_markup=back_keyboard())

    elif data == "update":
        await query.edit_message_text(
            "Формат:\n/update Cafe Day Person\nПриклад:\n/update DailyDose1 Wed Олена",
            reply_markup=back_keyboard(),
        )

    elif data == "template":
        template = "\n".join(
            [f"{c}:\nMon:\nTue:\nWed:\nThu:\nFri:\nSat:\nSun:\n" for c in GROUP_TOPICS.keys()]
        )
        await query.edit_message_text(f"Макет:\n\n{template}", reply_markup=back_keyboard())

    elif data == "addmix_btn":
        await query.edit_message_text("Відправ новий мікс:\n/addmix Текст", reply_markup=back_keyboard())

    elif data == "testsend":
        await send_daily(context)
        await query.edit_message_text("Тестова розсилка надіслана ✅", reply_markup=back_keyboard())


# ==========================
# ПРИЙОМ НОВОГО ГРАФІКУ
# ==========================

async def receive_next_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not WAITING_FOR_NEXT_SCHEDULE.get(user_id):
        return

    text = update.message.text
    new_schedule = empty_schedule_template()
    current_cafe = None

    for line in text.split("\n"):
        line = line.strip()

        if not line:
            continue

        if line.endswith(":") and line[:-1] in GROUP_TOPICS:
            current_cafe = line[:-1]
            continue

        if ":" in line and current_cafe:
            day, person = line.split(":", 1)
            day = day.strip()
            person = person.strip()

            if day in DAYS.values():
                new_schedule[current_cafe][day] = person

    save_next_schedule(new_schedule)
    WAITING_FOR_NEXT_SCHEDULE[user_id] = False
    await update.message.reply_text("✅ Новий графік збережено")


# ==========================
# ПЕРЕНЕСЕННЯ ГРАФІКУ
# ==========================

async def transfer_schedule(context: ContextTypes.DEFAULT_TYPE):
    next_schedule = load_next_schedule()

    if not any(any(person for person in cafe.values()) for cafe in next_schedule.values()):
        await context.bot.send_message(chat_id=ADMIN_ID, text="⚠️ Новий графік не заповнений!")
        return False

    save_schedule(next_schedule)
    save_next_schedule(empty_schedule_template())

    await context.bot.send_message(chat_id=ADMIN_ID, text="✅ Новий графік перенесено")
    return True


async def sunday_check(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now(timezone("Europe/Kyiv"))
    if now.weekday() != 6:
        return

    success = await transfer_schedule(context)

    if not success:
        context.job_queue.run_once(transfer_schedule, 3600)


# ==========================
# ІСНУЮЧИЙ ФУНКЦІОНАЛ
# ==========================

async def update_shift(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return

    cafe, day_short, person = context.args[0], context.args[1], " ".join(context.args[2:])
    schedule = load_schedule()
    schedule[cafe][DAYS[day_short]] = person
    save_schedule(schedule)

    await update.message.reply_text("Зміна оновлена ✅")


async def add_mix(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mix_text = " ".join(context.args)
    mixes = load_mixes()
    mixes.append(mix_text)
    save_mixes(mixes)
    await update.message.reply_text("✅ Мікс додано")


async def handle_mix(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text.strip().lower() != "#mixforme":
        return

    mixes = load_mixes()
    if not mixes:
        await update.message.reply_text("❌ База міксів порожня")
        return

    mix = random.choice(mixes)
    await update.message.reply_text(f"💨 Спробуй мікс:\n{mix}")


async def send_daily(context: ContextTypes.DEFAULT_TYPE):
    schedule = load_schedule()

    for cafe, ids in GROUP_TOPICS.items():
        msg = get_today_message(schedule, cafe)

        await context.bot.send_message(
            chat_id=ids["chat_id"],
            message_thread_id=ids["topic_id"],
            text=msg,
        )


# ==========================
# ЗАПУСК
# ==========================

def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("update", update_shift))
    app.add_handler(CommandHandler("addmix", add_mix))

    app.add_handler(MessageHandler(filters.TEXT & filters.ChatType.PRIVATE, receive_next_schedule))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.ChatType.PRIVATE, handle_mix))

    app.add_handler(CallbackQueryHandler(button_callback))

    app.job_queue.run_daily(
        send_daily,
        time(hour=12, minute=0, tzinfo=timezone("Europe/Kyiv"))
    )

    app.job_queue.run_daily(
        sunday_check,
        time(hour=22, minute=0, tzinfo=timezone("Europe/Kyiv"))
    )

    print("🤖 Bot started")
    app.run_polling()


if __name__ == "__main__":
    main()