# reports.py
from openpyxl import Workbook
from io import BytesIO
from aiogram.types import BufferedInputFile
from datetime import datetime, timedelta
from db import get_db
import re


goal_map = {
    "1": "похудение",
    "2": "набор мышечной массы",
    "3": "поддержание формы"
}

level_map = {
    "1": "новичок",
    "2": "средний",
    "3": "продвинутый"
}


def validate_full_name(text: str) -> bool:
    parts = text.strip().split()
    if len(parts) < 3:
        return False
    for part in parts:
        if len(part) < 2:
            return False
        if not re.match(r"^[a-zA-Zа-яА-ЯёЁ\-']+$", part):
            return False
    return True


def calculate_fitness_score(user_data: dict, logs: list) -> int:
    score = 0
    score += len(logs) * 3
    if logs:
        init = user_data["weight"]
        curr = logs[-1][0]
        goal = user_data["goal"]
        if goal == "похудение":
            kg = max(0, init - curr)
        elif goal == "набор мышечной массы":
            kg = max(0, curr - init)
        else:
            kg = min(12, len(logs))
        score += int(min(100, kg * 8))
        active_days = len({log[1].date() for log in logs})
        score += min(50, active_days // 3)
        first = min(log[1] for log in logs)
        months = (datetime.utcnow() - first).days // 30
        score += min(40, months * 5)
    return min(300, max(0, score))


async def can_export(user_id: int) -> tuple[bool, int]:
    conn = await get_db()
    row = await conn.fetchrow("SELECT last_export FROM users WHERE telegram_id = $1", user_id)
    await conn.close()
    if not row or not row['last_export']:
        return True, 0
    days = (datetime.utcnow() - row['last_export']).days
    return (days >= 30), max(0, 30 - days)


async def update_export_time(user_id: int):
    conn = await get_db()
    await conn.execute("UPDATE users SET last_export = NOW() WHERE telegram_id = $1", user_id)
    await conn.close()


def get_level_info(score: int):
    if score < 100:
        return "Новичок", "level1", "mon,wed,fri"
    elif score < 200:
        return "Средний", "level2", "mon,tue,thu,sat"
    else:
        return "Продвинутый", "level3", "mon,tue,wed,thu,fri,sat"


async def make_excel(user_data: dict, logs: list) -> BufferedInputFile:
    wb = Workbook()
    ws1 = wb.active
    ws1.title = "Прогресс"
    ws1.append(["Дата", "Вес (кг)"])
    for w, dt in logs:
        ws1.append([dt.strftime("%Y-%m-%d"), w])

    ws2 = wb.create_sheet("Анкета")
    ws2.append(["Параметр", "Значение"])
    ws2.append(["ФИО", user_data["full_name"]])
    ws2.append(["Рост (см)", user_data["height"]])
    ws2.append(["Начальный вес", user_data["weight"]])
    ws2.append(["Цель", user_data["goal"]])
    score = user_data.get("fitness_score", 0)
    level, _, _ = get_level_info(score)
    ws2.append(["Уровень", level])
    ws2.append(["Рейтинг", f"{score}/300"])

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return BufferedInputFile(buf.read(), "fitmind_report.xlsx")