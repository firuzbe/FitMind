import asyncio
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from datetime import datetime
from dotenv import load_dotenv
import os

from db import init_db, get_db
from agents import generate_plan, chat_with_ai
from reports import validate_full_name, goal_map, level_map
from scheduler import scheduler, setup_user_reminders

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_TELEGRAM_ID", 0))
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# -------------------- FSM States --------------------
class Form(StatesGroup):
    full_name = State()
    height = State()
    weight = State()
    goal = State()
    level = State()
    update_weight = State()
    reminder = State()

# -------------------- Inline Keyboards --------------------
def goal_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Похудение", callback_data="goal_1"),
                InlineKeyboardButton(text="Набор массы", callback_data="goal_2"),
                InlineKeyboardButton(text="Поддержание формы", callback_data="goal_3")
            ]
        ]
    )

def level_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Новичок", callback_data="level_1"),
                InlineKeyboardButton(text="Средний", callback_data="level_2"),
                InlineKeyboardButton(text="Продвинутый", callback_data="level_3")
            ]
        ]
    )

# -------------------- /start --------------------
@dp.message(F.text == "/start")
async def cmd_start(message: Message, state: FSMContext):
    conn = await get_db()
    user_row = await conn.fetchrow("SELECT * FROM users WHERE telegram_id = $1", message.from_user.id)
    await conn.close()

    if user_row:
        full_name = user_row['full_name']
        await message.answer(
            f"Привет, {full_name}! 👋\n"
            "Вы уже зарегистрированы. Выберите действие:\n"
            "/update — обновить вес\n"
            "/report — получить отчет\n"
            "/newplan — сгенерировать новый план\n"
            "/setreminder — установить напоминания\n"
            "/help — справка"
        )
        return

    first_name = message.from_user.first_name or "Друг"
    await message.answer(
        f"Привет, {first_name}! 👋\n\n"
        "Добро пожаловать в **FitMind** — вашу персональную фитнес-систему!\n"
        "Я — ваш виртуальный фитнес-коуч.\n\n"
        "Для начала регистрации введите Фамилию Имя Отчество."
    )
    await state.set_state(Form.full_name)

# -------------------- Регистрация --------------------
@dp.message(Form.full_name)
async def process_full_name(message: Message, state: FSMContext):
    if not validate_full_name(message.text):
        await message.answer("Введите полное ФИО через пробел.")
        return
    await state.update_data(full_name=message.text.strip())
    await message.answer("Укажите ваш рост (см):")
    await state.set_state(Form.height)

@dp.message(Form.height)
async def process_height(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Введите число (например: 175).")
        return
    await state.update_data(height=int(message.text))
    await message.answer("Теперь укажите ваш вес (кг):")
    await state.set_state(Form.weight)

@dp.message(Form.weight)
async def process_weight(message: Message, state: FSMContext):
    try:
        weight = float(message.text.replace(",", "."))
    except ValueError:
        await message.answer("Введите число (например: 70.5).")
        return
    await state.update_data(weight=weight)
    await message.answer("Выберите цель:", reply_markup=goal_keyboard())
    await state.set_state(Form.goal)

# -------------------- Callback для цели --------------------
@dp.callback_query(lambda c: c.data.startswith("goal_"))
async def process_goal_cb(callback_query: CallbackQuery, state: FSMContext):
    goal_key = callback_query.data.split("_")[1]
    goal = goal_map.get(goal_key)
    await state.update_data(goal=goal)
    await bot.send_message(callback_query.from_user.id, "Выберите уровень подготовки:", reply_markup=level_keyboard())
    await state.set_state(Form.level)

# -------------------- Callback для уровня --------------------
@dp.callback_query(lambda c: c.data.startswith("level_"))
async def process_level_cb(callback_query: CallbackQuery, state: FSMContext):
    level_key = callback_query.data.split("_")[1]
    level = level_map.get(level_key)
    data = await state.get_data()

    # Если данных нет, попросить пройти регистрацию заново
    if not data.get("full_name") or not data.get("height") or not data.get("weight") or not data.get("goal"):
        await bot.send_message(callback_query.from_user.id, "Произошла ошибка. Пожалуйста, введите /start и пройдите регистрацию заново.")
        await state.clear()
        return

    user_data = {
        "full_name": data["full_name"],
        "height": data["height"],
        "weight": data["weight"],
        "goal": data["goal"],
        "level": level,
        "fitness_score": 0,
        "coaching_mode": "level1"
    }

    # Генерация плана через ИИ
    plan = generate_plan(user_data)

    # Сохраняем пользователя в БД
    conn = await get_db()
    await conn.execute("""
        INSERT INTO users (telegram_id, username, full_name, height, weight, goal, fitness_score, coaching_mode)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
        ON CONFLICT (telegram_id) DO UPDATE SET
        full_name=$3, height=$4, weight=$5, goal=$6, fitness_score=$7, coaching_mode=$8
    """, callback_query.from_user.id, callback_query.from_user.username,
       user_data["full_name"], user_data["height"], user_data["weight"],
       user_data["goal"], user_data["fitness_score"], user_data["coaching_mode"])
    await conn.close()

    await bot.send_message(callback_query.from_user.id, f"✅ Ваш персональный фитнес-план:\n\n{plan}")
    await state.clear()

# -------------------- Общий чат с ИИ --------------------
@dp.message()
async def handle_general_message(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state:
        return  # обработка идет через FSM
    if message.text.startswith("/"):
        return
    response = chat_with_ai(message.text.strip())
    await message.answer(response)

# -------------------- /help --------------------
@dp.message(F.text == "/help")
async def cmd_help(message: Message):
    await message.answer(
        "💡 Команды:\n"
        "/start — регистрация\n"
        "/update — обновить вес\n"
        "/report — отчет и Excel\n"
        "/newplan — новый план\n"
        "/setreminder — установить напоминания\n"
        "/help — справка"
    )

# -------------------- /setreminder --------------------
@dp.message(F.text == "/setreminder")
async def cmd_set_reminder(message: Message, state: FSMContext):
    await message.answer(
        "Введите дни тренировок через запятую (например: mon,wed,fri) и время в формате HH:MM.\n"
        "Пример: mon,wed,fri 18:00"
    )
    await state.set_state(Form.reminder)

@dp.message(Form.reminder)
async def process_reminder(message: Message, state: FSMContext):
    try:
        parts = message.text.strip().split()
        days_str = parts[0].replace(" ", "").lower()
        hour, minute = map(int, parts[1].split(":"))

        # Проверка корректности дней
        valid_days = {"mon","tue","wed","thu","fri","sat","sun"}
        days_list = days_str.split(",")
        if not all(day in valid_days for day in days_list):
            await message.answer("Некорректные дни. Используйте: mon,tue,wed,thu,fri,sat,sun")
            return
        if not (0 <= hour < 24 and 0 <= minute < 60):
            await message.answer("Некорректное время. Часы: 0-23, минуты: 0-59")
            return

    except Exception:
        await message.answer("Неверный формат. Попробуйте снова: mon,wed,fri 18:00")
        return

    await setup_user_reminders(bot, message.from_user.id, days_str, hour, minute)
    await message.answer(f"✅ Напоминания установлены на: {days_str} в {hour:02d}:{minute:02d}")
    await state.clear()

# -------------------- Запуск --------------------
async def main():
    await init_db()
    scheduler.start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
