import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
TIMEZONE = os.getenv("TIMEZONE", "Asia/Novosibirsk")

if not BOT_TOKEN:
    raise RuntimeError(
        "Не найден BOT_TOKEN. Проверь файл .env"
    )

GROUP_NAME = "ИАТ-25"

# Опорная дата:
# 05.10.2026 — ЧЁТНАЯ неделя
ANCHOR_DATE = "2026-10-05"

# Текстовая информация для бота
UNIVERSITY_GROUP = "ИАТ-25"