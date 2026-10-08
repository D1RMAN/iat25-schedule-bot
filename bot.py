import logging
import re
import os
import threading

from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo

from flask import Flask

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
)

from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from config import BOT_TOKEN, TIMEZONE, GROUP_NAME

from schedule import (
    get_lessons,
    get_week_type,
    get_weekday_name,
)


# ============================================================
# НАСТРОЙКИ
# ============================================================

TZ = ZoneInfo(TIMEZONE)


# ============================================================
# WEB-СЕРВЕР ДЛЯ RENDER
# ============================================================

web_app = Flask(__name__)


@web_app.route("/")
def home():
    return "IAT-25 Telegram Bot is running!"


@web_app.route("/health")
def health():
    return "OK"


def run_web_server():

    port = int(
        os.environ.get(
            "PORT",
            10000
        )
    )

    web_app.run(
        host="0.0.0.0",
        port=port,
    )


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)


# ============================================================
# КЛАВИАТУРА
# ============================================================

MAIN_KEYBOARD = [
    [
        KeyboardButton("📅 Сегодня"),
        KeyboardButton("🔜 Завтра"),
    ],
    [
        KeyboardButton("📆 Послезавтра"),
        KeyboardButton("📋 Эта неделя"),
    ],
    [
        KeyboardButton("➡️ Следующая неделя"),
        KeyboardButton("🔎 Выбрать дату"),
    ],
    [
        KeyboardButton("ℹ️ Помощь"),
    ],
]


def get_main_keyboard():

    return ReplyKeyboardMarkup(
        MAIN_KEYBOARD,
        resize_keyboard=True,
        is_persistent=True,
    )


# ============================================================
# ТЕКУЩАЯ ДАТА
# ============================================================

def now():

    return datetime.now(TZ)


# ============================================================
# ФОРМАТ ДАТЫ
# ============================================================

def format_date(target_date: date):

    months = [
        "",
        "января",
        "февраля",
        "марта",
        "апреля",
        "мая",
        "июня",
        "июля",
        "августа",
        "сентября",
        "октября",
        "ноября",
        "декабря",
    ]

    return (
        f"{target_date.day} "
        f"{months[target_date.month]} "
        f"{target_date.year}"
    )


# ============================================================
# ЭМОДЗИ НЕДЕЛИ
# ============================================================

def week_emoji(week_type):

    if week_type == "Чётная":
        return "🟢"

    return "🔵"


# ============================================================
# ФОРМАТИРОВАНИЕ ПАРЫ
# ============================================================

def format_lesson(item):

    if item.number == 0:
        return f"📚 <b>{item.subject}</b>"

    result = (
        f"<b>{item.number}. {item.subject}</b>"
    )

    if item.teacher:
        result += (
            f"\n   👨‍🏫 {item.teacher}"
        )

    if item.room:
        result += (
            f"\n   🚪 ауд. {item.room}"
        )

    return result


# ============================================================
# РАСПИСАНИЕ НА ДЕНЬ
# ============================================================

def build_day_message(target_date):

    weekday = get_weekday_name(target_date)
    week_type = get_week_type(target_date)

    lessons = get_lessons(target_date)

    text = ""

    text += (
        f"📅 <b>{format_date(target_date)}</b>\n"
    )

    text += (
        f"🗓 {weekday}\n"
    )

    if weekday not in [
        "Четверг",
        "Пятница",
        "Суббота",
        "Воскресенье",
    ]:

        text += (
            f"{week_emoji(week_type)} "
            f"<b>{week_type} неделя</b>\n"
        )

    text += "\n"

    if not lessons:

        text += "🎉 <b>Занятий нет.</b>"

        return text

    if (
        len(lessons) == 1
        and lessons[0].number == 0
    ):

        text += (
            f"📚 <b>{lessons[0].subject}</b>"
        )

        return text

    shown = False

    for item in lessons:

        if item.subject == "Нет занятий":
            continue

        text += format_lesson(item)
        text += "\n\n"

        shown = True

    if not shown:

        return (
            f"📅 <b>{format_date(target_date)}</b>\n"
            f"🗓 {weekday}\n\n"
            "🎉 <b>Занятий нет.</b>"
        )

    return text.rstrip()


# ============================================================
# РАСПИСАНИЕ НА НЕДЕЛЮ
# ============================================================

def build_week_message(start_date):

    week_type = get_week_type(start_date)

    end_date = start_date + timedelta(days=6)

    text = ""

    text += "📚 <b>РАСПИСАНИЕ НА НЕДЕЛЮ</b>\n\n"

    text += (
        f"{week_emoji(week_type)} "
        f"<b>{week_type.upper()} НЕДЕЛЯ</b>\n"
    )

    text += (
        f"📅 "
        f"{start_date.strftime('%d.%m.%Y')}"
        f" — "
        f"{end_date.strftime('%d.%m.%Y')}\n\n"
    )

    for i in range(7):

        target = start_date + timedelta(days=i)

        weekday = get_weekday_name(target)

        text += (
            f"━━━━━━━━━━━━━━━━━━\n"
            f"<b>{weekday}</b>\n"
        )

        lessons = get_lessons(target)

        if not lessons:

            text += "— занятий нет\n\n"

            continue

        if (
            len(lessons) == 1
            and lessons[0].number == 0
        ):

            text += (
                f"📚 {lessons[0].subject}\n\n"
            )

            continue

        has_lessons = False

        for item in lessons:

            if item.subject == "Нет занятий":
                continue

            has_lessons = True

            text += (
                f"{item.number}. "
                f"{item.subject}"
            )

            if item.room:
                text += (
                    f" — {item.room}"
                )

            text += "\n"

        if not has_lessons:

            text += "— занятий нет\n"

        text += "\n"

    return text.rstrip()


# ============================================================
# ПАРСИНГ ДАТЫ
# ============================================================

def parse_date(text):

    text = text.strip()

    formats = [
        "%d.%m.%Y",
        "%d.%m",
        "%d-%m-%Y",
        "%d-%m",
    ]

    for fmt in formats:

        try:

            parsed = datetime.strptime(
                text,
                fmt
            )

            if "%Y" not in fmt:

                return date(
                    now().year,
                    parsed.month,
                    parsed.day,
                )

            return parsed.date()

        except ValueError:

            continue

    return None


# ============================================================
# /START
# ============================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    user = update.effective_user

    text = (
        f"👋 <b>Привет, {user.first_name}!</b>\n\n"
        f"📚 Я бот расписания группы "
        f"<b>{GROUP_NAME}</b>.\n\n"
        "🟢 Чётная неделя\n"
        "🔵 Нечётная неделя\n\n"
        "📌 <b>05.10.2026 — чётная неделя</b>\n\n"
        "Выбирай нужное действие кнопками ниже 👇"
    )

    await update.message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=get_main_keyboard(),
    )


# ============================================================
# ПОМОЩЬ
# ============================================================

async def show_help(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    text = """
ℹ️ <b>ПОМОЩЬ</b>

📅 <b>Сегодня</b>
Показывает пары на сегодня.

🔜 <b>Завтра</b>
Показывает пары на завтра.

📆 <b>Послезавтра</b>
Показывает пары через два дня.

📋 <b>Эта неделя</b>
Показывает расписание текущей недели.

➡️ <b>Следующая неделя</b>
Показывает расписание следующей недели.

🔎 <b>Выбрать дату</b>
Позволяет посмотреть расписание на любую дату.

Также работают команды:

/today
/tomorrow
/day 12.10
/week
/next
"""

    await update.message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=get_main_keyboard(),
    )


# ============================================================
# СЕГОДНЯ
# ============================================================

async def show_today(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    target = now().date()

    text = (
        "📖 <b>СЕГОДНЯ</b>\n\n"
        + build_day_message(target)
    )

    await update.message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=get_main_keyboard(),
    )


# ============================================================
# ЗАВТРА
# ============================================================

async def show_tomorrow(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    target = now().date() + timedelta(days=1)

    text = (
        "📖 <b>ЗАВТРА</b>\n\n"
        + build_day_message(target)
    )

    await update.message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=get_main_keyboard(),
    )


# ============================================================
# ПОСЛЕЗАВТРА
# ============================================================

async def show_day_after_tomorrow(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    target = now().date() + timedelta(days=2)

    text = (
        "📖 <b>ПОСЛЕЗАВТРА</b>\n\n"
        + build_day_message(target)
    )

    await update.message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=get_main_keyboard(),
    )


# ============================================================
# ЭТА НЕДЕЛЯ
# ============================================================

async def show_current_week(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    today = now().date()

    monday = (
        today
        - timedelta(days=today.weekday())
    )

    text = build_week_message(monday)

    await update.message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=get_main_keyboard(),
    )


# ============================================================
# СЛЕДУЮЩАЯ НЕДЕЛЯ
# ============================================================

async def show_next_week(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    today = now().date()

    monday = (
        today
        - timedelta(days=today.weekday())
    )

    next_monday = (
        monday + timedelta(days=7)
    )

    text = build_week_message(
        next_monday
    )

    await update.message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=get_main_keyboard(),
    )


# ============================================================
# ВЫБОР ДАТЫ
# ============================================================

async def ask_date(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    context.user_data["waiting_for_date"] = True

    await update.message.reply_text(
        "🔎 <b>Выбор даты</b>\n\n"
        "Напиши дату в формате:\n\n"
        "<code>15.10</code>\n\n"
        "или:\n\n"
        "<code>15.10.2026</code>",
        parse_mode="HTML",
        reply_markup=get_main_keyboard(),
    )


# ============================================================
# ОБРАБОТКА ДАТЫ
# ============================================================

async def process_date(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    text = update.message.text.strip()

    target = parse_date(text)

    if target is None:

        await update.message.reply_text(
            "❌ Не смог распознать дату.\n\n"
            "Например:\n"
            "<code>15.10</code>",
            parse_mode="HTML",
            reply_markup=get_main_keyboard(),
        )

        return

    context.user_data[
        "waiting_for_date"
    ] = False

    answer = build_day_message(
        target
    )

    await update.message.reply_text(
        "🔎 <b>РАСПИСАНИЕ НА ВЫБРАННУЮ ДАТУ</b>\n\n"
        + answer,
        parse_mode="HTML",
        reply_markup=get_main_keyboard(),
    )


# ============================================================
# ОБРАБОТКА ТЕКСТА И КНОПОК
# ============================================================

async def text_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not update.message:
        return

    text = update.message.text.strip()

    # Режим выбора даты
    if context.user_data.get(
        "waiting_for_date",
        False
    ):

        await process_date(
            update,
            context
        )

        return

    # Кнопки
    if text == "📅 Сегодня":

        await show_today(
            update,
            context
        )
        return

    if text == "🔜 Завтра":

        await show_tomorrow(
            update,
            context
        )
        return

    if text == "📆 Послезавтра":

        await show_day_after_tomorrow(
            update,
            context
        )
        return

    if text == "📋 Эта неделя":

        await show_current_week(
            update,
            context
        )
        return

    if text == "➡️ Следующая неделя":

        await show_next_week(
            update,
            context
        )
        return

    if text == "🔎 Выбрать дату":

        await ask_date(
            update,
            context
        )
        return

    if text == "ℹ️ Помощь":

        await show_help(
            update,
            context
        )
        return

    # Обычный текст
    lower = text.lower()

    today = now().date()

    if "послезавтра" in lower:

        await show_day_after_tomorrow(
            update,
            context
        )
        return

    if "завтра" in lower:

        await show_tomorrow(
            update,
            context
        )
        return

    if "сегодня" in lower:

        await show_today(
            update,
            context
        )
        return

    # Дни недели
    weekdays = {
        "понедельник": 0,
        "вторник": 1,
        "среда": 2,
        "среду": 2,
        "четверг": 3,
        "пятница": 4,
        "пятницу": 4,
        "суббота": 5,
        "воскресенье": 6,
    }

    for word, weekday_number in weekdays.items():

        if word in lower:

            monday = (
                today
                - timedelta(
                    days=today.weekday()
                )
            )

            target = (
                monday
                + timedelta(
                    days=weekday_number
                )
            )

            if target < today:

                target += timedelta(days=7)

            answer = build_day_message(
                target
            )

            await update.message.reply_text(
                answer,
                parse_mode="HTML",
                reply_markup=get_main_keyboard(),
            )

            return

    # Дата в тексте
    match = re.search(
        r"\b(\d{1,2}[./-]\d{1,2}"
        r"(?:[./-]\d{4})?)\b",
        lower,
    )

    if match:

        date_text = (
            match.group(1)
            .replace("/", ".")
            .replace("-", ".")
        )

        target = parse_date(
            date_text
        )

        if target:

            answer = build_day_message(
                target
            )

            await update.message.reply_text(
                answer,
                parse_mode="HTML",
                reply_markup=get_main_keyboard(),
            )

            return

    await update.message.reply_text(
        "🤔 Не совсем понял.\n\n"
        "Используй кнопки ниже 👇",
        reply_markup=get_main_keyboard(),
    )


# ============================================================
# КОМАНДЫ
# ============================================================

async def today_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    await show_today(
        update,
        context
    )


async def tomorrow_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    await show_tomorrow(
        update,
        context
    )


async def day_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not context.args:

        await ask_date(
            update,
            context
        )
        return

    target = parse_date(
        context.args[0]
    )

    if target is None:

        await update.message.reply_text(
            "❌ Неверный формат даты.\n\n"
            "Например:\n"
            "/day 15.10",
            reply_markup=get_main_keyboard(),
        )

        return

    answer = build_day_message(
        target
    )

    await update.message.reply_text(
        answer,
        parse_mode="HTML",
        reply_markup=get_main_keyboard(),
    )


async def week_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    await show_current_week(
        update,
        context
    )


async def next_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    await show_next_week(
        update,
        context
    )


# ============================================================
# ОБРАБОТКА ОШИБОК
# ============================================================

async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE,
):

    logger.error(
        "Ошибка:",
        exc_info=context.error
    )


# ============================================================
# ЗАПУСК
# ============================================================

def main():

    # Запускаем HTTP-сервер для Render
    web_thread = threading.Thread(
        target=run_web_server,
        daemon=True,
    )

    web_thread.start()

    print("=" * 60)
    print("БОТ РАСПИСАНИЯ ИАТ-25")
    print("=" * 60)

    print(
        f"Часовой пояс: {TIMEZONE}"
    )

    print(
        "05.10.2026 = ЧЁТНАЯ НЕДЕЛЯ"
    )

    print("=" * 60)
    print("HTTP-сервер запущен.")
    print("Telegram-бот запускается...")
    print("=" * 60)

    application = (
        Application
        .builder()
        .token(BOT_TOKEN)
        .build()
    )

    # Команды
    application.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    application.add_handler(
        CommandHandler(
            "help",
            show_help
        )
    )

    application.add_handler(
        CommandHandler(
            "today",
            today_command
        )
    )

    application.add_handler(
        CommandHandler(
            "tomorrow",
            tomorrow_command
        )
    )

    application.add_handler(
        CommandHandler(
            "day",
            day_command
        )
    )

    application.add_handler(
        CommandHandler(
            "week",
            week_command
        )
    )

    application.add_handler(
        CommandHandler(
            "next",
            next_command
        )
    )

    # Текст / кнопки
    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            text_handler
        )
    )

    application.add_error_handler(
        error_handler
    )

    application.run_polling(
        allowed_updates=Update.ALL_TYPES
    )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    main()