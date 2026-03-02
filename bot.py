import json
import os
import random
import logging
from datetime import datetime, time
from pytz import timezone
from typing import Optional, Dict, Any, List

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

# === Налаштування логування ===
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-5s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# === Конфігурація ===
TOKEN = os.getenv("TOKEN").strip()

ADMIN_ID = 662089451

SCHEDULE_FILE = "schedule.json"
NEXT_SCHEDULE_FILE = "next_schedule.json"
MIXES_FILE = "mixes.json"

KYIV = timezone("Europe/Kyiv")

GROUP_TOPICS = {
    "DailyDose1": {"chat_id": -1002299751427, "topic_id": 225},
    "DailyDose2": {"chat_id": -1002299751427, "topic_id": 230},
    "DailyDose3": {"chat_id": -1002299751427, "topic_id": 227},
    "Citadell":   {"chat_id": -1002299751427, "topic_id": 901},
    "Rafael":     {"chat_id": -1002299751427, "topic_id": 2389},
}

DAYS = {
    "Mon": "Monday", "Tue": "Tuesday", "Wed": "Wednesday",
    "Thu": "Thursday", "Fri": "Friday", "Sat": "Saturday", "Sun": "Sunday",
}

STATE_NEXT_SCHEDULE_EDIT = "next_schedule_edit_mode"

# === Допоміжні функції ===
def save_json(path: str, data: Any, description: str = "") -> None:
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        count = len(data) if isinstance(data, (dict, list)) else "—"
        logger.info(f"Збережено {description}: {path} ({count} елементів)")
    except Exception as e:
        logger.error(f"Помилка збереження {path}: {e}", exc_info=True)


def load_json(path: str, default: Any) -> Any:
    if not os.path.exists(path):
        save_json(path, default, f"створено початковий файл {path}")
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Помилка читання {path}: {e}", exc_info=True)
        return default


def load_schedule() -> Dict:
    return load_json(SCHEDULE_FILE, {})


def save_schedule(schedule: Dict) -> None:
    save_json(SCHEDULE_FILE, schedule, "графік змін")


def load_next_schedule() -> Dict:
    return load_json(NEXT_SCHEDULE_FILE, {})


def save_next_schedule(schedule: Dict) -> None:
    save_json(NEXT_SCHEDULE_FILE, schedule, "наступний графік")


def load_mixes() -> List[str]:
    return load_json(MIXES_FILE, [])


def save_mixes(mixes: List[str]) -> None:
    save_json(MIXES_FILE, mixes, "мікси")


def empty_schedule_template() -> Dict:
    return {cafe: {day: "" for day in DAYS.values()} for cafe in GROUP_TOPICS}


def get_today_message(schedule: Dict, cafe: Optional[str] = None) -> str:
    today = datetime.now(KYIV).strftime("%A")
    if cafe:
        person = schedule.get(cafe, {}).get(today, "Ніхто не запланований")
        return f"📅 Сьогодні на зміні: {person}"
    
    lines = ["📅 Сьогодні на зміні:\n"]
    for c in GROUP_TOPICS:
        person = schedule.get(c, {}).get(today, "Ніхто не запланований")
        lines.append(f"{c}: {person}")
    return "\n".join(lines)


# === Клавіатури ===
def get_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📅 Показати сьогодні", callback_data="show")],
        [InlineKeyboardButton("🗓 Графік на тиждень", callback_data="show_week")],
        [InlineKeyboardButton("🆕 Новий графік на наступний тиждень", callback_data="new_next_week")],
        [InlineKeyboardButton("🔄 Змінити зміну", callback_data="update")],
        [InlineKeyboardButton("📝 Макет графіку", callback_data="template")],
        [InlineKeyboardButton("➕ Додати мікс", callback_data="addmix_btn")],
        [InlineKeyboardButton("📨 Тестова розсилка", callback_data="testsend")],
    ])


def get_back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]])


# === HANDLERS ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ADMIN_ID:
        return

    text = "Привіт! Використовуй меню нижче:"
    if update.effective_chat.type != "private":
        await context.bot.send_message(
            chat_id=update.effective_user.id,
            text=text,
            reply_markup=get_main_keyboard()
        )
    else:
        await update.message.reply_text(text, reply_markup=get_main_keyboard())


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    if query.from_user.id != ADMIN_ID:
        return

    data = query.data

    if data == "back_to_main":
        context.user_data.pop(STATE_NEXT_SCHEDULE_EDIT, None)
        await query.edit_message_text("Привіт! Використовуй меню нижче:", reply_markup=get_main_keyboard())
        return

    if data == "show":
        schedule = load_schedule()
        await query.edit_message_text(get_today_message(schedule), reply_markup=get_back_keyboard())

    elif data == "show_week":
        schedule = load_schedule()
        lines = ["🗓 Графік на тиждень:\n"]
        for cafe, shifts in schedule.items():
            lines.append(f"{cafe}:")
            for day, person in shifts.items():
                lines.append(f"  {day}: {person or '—'}")
            lines.append("")
        await query.edit_message_text("\n".join(lines), reply_markup=get_back_keyboard())

    elif data == "new_next_week":
        next_s = empty_schedule_template()
        save_next_schedule(next_s)

        context.user_data[STATE_NEXT_SCHEDULE_EDIT] = True

        text = (
            "🆕 <b>Режим заповнення графіку на наступний тиждень</b>\n\n"
            "Надсилай графік у такому форматі (можна кілька закладів одразу):\n\n"
            "<code>DailyDose1:\n"
            "Monday: Денис\n"
            "Tuesday: Денис\n"
            "...\n\n"
            "DailyDose2:\n"
            "Monday: Олексій\n"
            "...\n</code>\n\n"
            "Після введення натисни «Зберегти та вийти» — графік автоматично активується як поточний."
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("💾 Зберегти та вийти", callback_data="save_and_exit_next")],
            [InlineKeyboardButton("❌ Скасувати", callback_data="cancel_next")],
            [InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]
        ])
        await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")
        return

    elif data == "save_and_exit_next":
        if STATE_NEXT_SCHEDULE_EDIT not in context.user_data:
            await query.edit_message_text("Режим редагування вже завершено.", reply_markup=get_back_keyboard())
            return

        next_s = load_next_schedule()
        text = "✅ Графік збережено та активовано як поточний!\n\n"
        for cafe, shifts in next_s.items():
            text += f"<b>{cafe}:</b>\n"
            for day, p in shifts.items():
                text += f"  {day}: {p or '—'}\n"
            text += "\n"

        # Автоматично пушимо в основний schedule
        save_schedule(next_s)
        save_next_schedule({})

        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]
        ])

        context.user_data.pop(STATE_NEXT_SCHEDULE_EDIT, None)

        await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")
        return

    elif data == "cancel_next":
        context.user_data.pop(STATE_NEXT_SCHEDULE_EDIT, None)
        save_next_schedule({})
        await query.edit_message_text("Редагування скасовано. Наступний графік очищено.", reply_markup=get_back_keyboard())
        return

    elif data == "update":
        await query.edit_message_text(
            "Формат:\n/update Cafe Day Person\nПриклад:\n/update DailyDose1 Wed Олена",
            reply_markup=get_back_keyboard()
        )

    elif data == "template":
        template = "\n".join(
            f"{c}:\n" + "\n".join(f"{d}:" for d in DAYS.values())
            for c in GROUP_TOPICS
        )
        await query.edit_message_text(f"Макет графіку:\n\n{template}", reply_markup=get_back_keyboard())

    elif data == "addmix_btn":
        await query.edit_message_text("Відправ:\n/addmix Текст міксу", reply_markup=get_back_keyboard())

    elif data == "testsend":
        await send_daily(context)
        await query.edit_message_text("Тестова розсилка виконана ✅", reply_markup=get_back_keyboard())


async def update_shift(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ADMIN_ID:
        return

    if len(context.args) < 3:
        await update.message.reply_text("Формат: /update Cafe Day Person\nПриклад: /update DailyDose1 Wed Олена")
        return

    cafe, day_short, *person_parts = context.args
    person = " ".join(person_parts)

    day_short = day_short.capitalize()
    if day_short not in DAYS:
        await update.message.reply_text("День: Mon Tue Wed Thu Fri Sat Sun")
        return

    schedule = load_schedule()
    if cafe not in schedule:
        await update.message.reply_text(f"Заклад '{cafe}' не знайдено")
        return

    full_day = DAYS[day_short]
    old = schedule[cafe].get(full_day, "—")
    schedule[cafe][full_day] = person
    save_schedule(schedule)

    await update.message.reply_text(
        f"Оновлено:\n{cafe} {full_day}: {old} → {person}"
    )


async def add_mix(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ADMIN_ID:
        return

    if not context.args:
        await update.message.reply_text("Формат: /addmix Текст міксу")
        return

    mix_text = " ".join(context.args).strip()
    if not mix_text:
        await update.message.reply_text("Текст міксу порожній")
        return

    mixes = load_mixes()
    mixes.append(mix_text)
    save_mixes(mixes)
    await update.message.reply_text(f"Мікс додано ({len(mixes)} шт)")


async def handle_mix(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return

    text = update.message.text.strip().lower()
    if text != "#mixforme":
        return

    chat_id = update.effective_chat.id
    topic_id = update.message.message_thread_id

    if not any(
        d["chat_id"] == chat_id and d["topic_id"] == topic_id
        for d in GROUP_TOPICS.values()
    ):
        return

    mixes = load_mixes()
    if not mixes:
        await update.message.reply_text("База міксів порожня 😔")
        return

    mix = random.choice(mixes)
    await update.message.reply_text(f"💨 Спробуй цей мікс:\n{mix}")


async def handle_next_week_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ADMIN_ID:
        return

    if STATE_NEXT_SCHEDULE_EDIT not in context.user_data:
        return

    if not update.message or not update.message.text:
        return

    text = update.message.text.strip()
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    next_schedule = load_next_schedule()
    updated_count = 0
    errors = []
    current_cafe = None

    for line in lines:
        line = line.replace('\xa0', ' ').strip()  # прибираємо невидимі пробіли

        if line.endswith(':') and len(line) > 1:
            cafe_candidate = line[:-1].strip()
            if cafe_candidate in GROUP_TOPICS:
                current_cafe = cafe_candidate
                continue
            else:
                errors.append(f"Невідомий заклад: {line}")
                current_cafe = None
                continue

        if not current_cafe:
            errors.append(f"Рядок без закладу: {line}")
            continue

        if ':' not in line:
            errors.append(f"Немає двокрапки: {line}")
            continue

        day_part, person_part = [x.strip() for x in line.split(':', 1)]
        person = person_part

        # шукаємо день (повне ім'я або скорочення)
        day_short = None
        day_candidate_lower = day_part.lower()
        for short, full in DAYS.items():
            if day_candidate_lower == full.lower() or day_candidate_lower == short.lower():
                day_short = short
                break

        if not day_short:
            errors.append(f"Нерозпізнаний день: {day_part}")
            continue

        full_day = DAYS[day_short]

        next_schedule[current_cafe][full_day] = person
        updated_count += 1

    if updated_count > 0:
        save_next_schedule(next_schedule)

    reply = f"✅ Оновлено {updated_count} позицій"
    if errors:
        reply += "\n\nНе розпізнано / помилки:\n" + "\n".join(f"• {e}" for e in errors[:12])
        if len(errors) > 12:
            reply += f"\n... та ще {len(errors)-12} рядків"

    await update.message.reply_text(reply)


async def send_daily(context: ContextTypes.DEFAULT_TYPE) -> None:
    schedule = load_schedule()
    for cafe, ids in GROUP_TOPICS.items():
        msg = get_today_message(schedule, cafe)
        try:
            await context.bot.send_message(
                chat_id=ids["chat_id"],
                message_thread_id=ids["topic_id"],
                text=msg,
            )
            logger.info(f"Надіслано графік для {cafe}")
        except Exception as e:
            logger.error(f"Помилка розсилки {cafe}: {e}")


async def activate_next_schedule_sunday(context: ContextTypes.DEFAULT_TYPE) -> None:
    now = datetime.now(KYIV)
    if now.weekday() != 6:
        return

    next_data = load_next_schedule()
    if not next_data or all(all(not v for v in shifts.values()) for shifts in next_data.values()):
        logger.info("next_schedule порожній — пропускаємо")
        return

    logger.info("Активація нового графіку (неділя 22:00)")
    save_schedule(next_data)
    save_next_schedule({})
    logger.info("Новий графік активовано")


async def debugsched(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ADMIN_ID:
        return

    sch = load_schedule()
    nxt = load_next_schedule()
    mixes_cnt = len(load_mixes())

    text = (
        f"🛠 DEBUG\n\n"
        f"schedule.json ({len(sch)}):\n{json.dumps(sch, ensure_ascii=False, indent=1)}\n\n"
        f"next_schedule.json ({len(nxt)}):\n{json.dumps(nxt, ensure_ascii=False, indent=1)}\n\n"
        f"Міксів: {mixes_cnt}"
    )
    await update.message.reply_text(text)


def main() -> None:
    if not TOKEN:
        logger.critical("TOKEN не заданий!")
        return

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("update", update_shift))
    app.add_handler(CommandHandler("addmix", add_mix))
    app.add_handler(CommandHandler("debugsched", debugsched))

    app.add_handler(CallbackQueryHandler(button_callback))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.ChatType.PRIVATE, handle_mix))
    app.add_handler(MessageHandler(filters.TEXT & filters.ChatType.PRIVATE, handle_next_week_input))

    app.job_queue.run_daily(
        send_daily,
        time(hour=12, minute=0, tzinfo=KYIV)
    )

    app.job_queue.run_daily(
        activate_next_schedule_sunday,
        time(hour=22, minute=0, tzinfo=KYIV),
        days=(6,)
    )

    logger.info("🤖 Бот запущено")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()