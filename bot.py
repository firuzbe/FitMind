import asyncio
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery, BufferedInputFile
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from dotenv import load_dotenv
import os

from db import init_db, get_db
from agents import generate_plan, chat_with_ai
from reports import validate_full_name, goal_map, level_map, make_excel
from scheduler import scheduler, setup_user_reminders

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()


# ----------------------------------------------------------
# FSM
# ----------------------------------------------------------
class Form(StatesGroup):
    full_name = State()
    height = State()
    weight = State()
    goal = State()
    level = State()
    update_weight = State()
    reminder = State()


# ----------------------------------------------------------
# Keyboards
# ----------------------------------------------------------
def goal_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Похудение", callback_data="goal_1"),
            InlineKeyboardButton(text="Набор массы", callback_data="goal_2"),
            InlineKeyboardButton(text="Поддержание формы", callback_data="goal_3")
        ]
    ])


def level_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Новичок", callback_data="level_1"),
            InlineKeyboardButton(text="Средний", callback_data="level_2"),
            InlineKeyboardButton(text="Продвинутый", callback_data="level_3")
        ]
    ])


# ----------------------------------------------------------
# /start
# ----------------------------------------------------------
@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()

    conn = await get_db()
    user = await conn.fetchrow("SELECT * FROM users WHERE telegram_id=$1", message.from_user.id)
    await conn.close()

    if user:
        await message.answer(
            f"Привет, {user['full_name']}!\n"
            "Вы уже зарегистрированы. Выберите действие:\n\n"
            "/update — обновить вес\n"
            "/report — получить отчет\n"
            "/newplan — сгенерировать новый план\n"
            "/setreminder — установить напоминания\n"
            "/help — справка"
        )
        return

    await message.answer(
        "Добро пожаловать в FitMind!\nВведите Фамилию Имя Отчество:"
    )
    await state.set_state(Form.full_name)


# ----------------------------------------------------------
# Регистрация
# ----------------------------------------------------------
@dp.message(Form.full_name)
async def process_full_name(message: Message, state: FSMContext):
    if not validate_full_name(message.text):
        await message.answer("Введите ФИО через пробел.")
        return

    await state.update_data(full_name=message.text.strip())
    await message.answer("Введите ваш рост (см):")
    await state.set_state(Form.height)


@dp.message(Form.height)
async def process_height(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Только число.")
        return

    await state.update_data(height=int(message.text))
    await message.answer("Введите ваш вес (кг):")
    await state.set_state(Form.weight)


@dp.message(Form.weight)
async def process_weight(message: Message, state: FSMContext):
    try:
        weight = float(message.text.replace(",", "."))
    except:
        await message.answer("Введите число.")
        return

    await state.update_data(weight=weight)
    await message.answer("Выберите цель:", reply_markup=goal_keyboard())
    await state.set_state(Form.goal)


@dp.callback_query(F.data.startswith("goal_"))
async def process_goal_cb(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    goal_key = callback.data.split("_")[1]
    await state.update_data(goal=goal_map.get(goal_key))
    await callback.message.answer("Выберите уровень:", reply_markup=level_keyboard())
    await state.set_state(Form.level)


@dp.callback_query(F.data.startswith("level_"))
async def process_level_cb(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    level_key = callback.data.split("_")[1]
    level_value = level_map.get(level_key)

    data = await state.get_data()

    # Проверка на случай сбоя FSM
    for key in ["full_name", "height", "weight", "goal"]:
        if key not in data:
            await callback.message.answer("Регистрация нарушена. Введите /start и повторите.")
            await state.clear()
            return

    user_data = {
        "full_name": data["full_name"],
        "height": data["height"],
        "weight": data["weight"],
        "goal": data["goal"],
        "level": level_value,
        "fitness_score": 0,
        "coaching_mode": "level1"
    }

    # Генерация плана
    plan = generate_plan(user_data)

    # Сохранение
    conn = await get_db()
    await conn.execute("""
        INSERT INTO users (telegram_id, username, full_name, height, weight, goal, fitness_score, coaching_mode)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
        ON CONFLICT (telegram_id) DO UPDATE SET full_name=$3,height=$4,weight=$5,goal=$6
    """,
                       callback.from_user.id, callback.from_user.username,
                       user_data["full_name"], user_data["height"], user_data["weight"],
                       user_data["goal"], user_data["fitness_score"], user_data["coaching_mode"]
                       )
    await conn.close()

    await callback.message.answer(f"Ваш персональный план:\n\n{plan}")
    await state.clear()


# ----------------------------------------------------------
# /update — обновление веса
# ----------------------------------------------------------
@dp.message(Command("update"))
async def cmd_update(message: Message, state: FSMContext):
    await state.clear()

    conn = await get_db()
    user = await conn.fetchrow("SELECT * FROM users WHERE telegram_id=$1", message.from_user.id)
    await conn.close()

    if not user:
        await message.answer("Сначала зарегистрируйтесь через /start")
        return

    await message.answer("Введите новый вес (кг):")
    await state.set_state(Form.update_weight)


@dp.message(Form.update_weight)
async def update_weight(message: Message, state: FSMContext):
    try:
        weight = float(message.text.replace(",", "."))
    except:
        await message.answer("Введите число.")
        return

    conn = await get_db()
    # Сохраняем вес в users
    await conn.execute("UPDATE users SET weight=$1 WHERE telegram_id=$2", weight, message.from_user.id)
    # Также сохраняем в логи прогресса
    await conn.execute("""
        INSERT INTO progress_logs (telegram_id, weight) 
        VALUES ($1, $2)
    """, message.from_user.id, weight)
    await conn.close()

    await message.answer("Вес обновлён.")
    await state.clear()


# ----------------------------------------------------------
# /newplan — новый план
# ----------------------------------------------------------
@dp.message(Command("newplan"))
async def cmd_newplan(message: Message):
    conn = await get_db()
    user = await conn.fetchrow("SELECT * FROM users WHERE telegram_id=$1", message.from_user.id)
    await conn.close()

    if not user:
        await message.answer("Вы не зарегистрированы. Введите /start.")
        return

    plan = generate_plan(dict(user))
    await message.answer(f"Ваш новый план:\n\n{plan}")


# ----------------------------------------------------------
# /report — отчёт
# ----------------------------------------------------------
@dp.message(Command("report"))
async def cmd_report(message: Message):
    conn = await get_db()
    user = await conn.fetchrow("SELECT * FROM users WHERE telegram_id=$1", message.from_user.id)

    if not user:
        await conn.close()
        await message.answer("Вы не зарегистрированы. Введите /start.")
        return

    # Получаем логи прогресса
    logs = await conn.fetch(
        "SELECT weight, recorded_at FROM progress_logs WHERE telegram_id=$1 ORDER BY recorded_at",
        message.from_user.id
    )
    await conn.close()

    # Преобразуем логи в нужный формат
    log_list = [(log['weight'], log['recorded_at']) for log in logs]

    # Получаем данные пользователя в виде словаря
    user_dict = dict(user)

    # Генерируем Excel файл
    excel_file = await make_excel(user_dict, log_list)

    # Отправляем файл
    await message.answer_document(excel_file)


# ----------------------------------------------------------
# /help
# ----------------------------------------------------------
@dp.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "<b>Доступные команды:</b>\n\n"
        "/start — регистрация или приветствие\n"
        "/update — обновить вес\n"
        "/report — получить отчет\n"
        "/newplan — сгенерировать новый план\n"
        "/setreminder — установить напоминания\n"
        "/help — справка"
    )


# ----------------------------------------------------------
# Напоминания
# ----------------------------------------------------------
@dp.message(Command("setreminder"))
async def cmd_setreminder(message: Message, state: FSMContext):
    conn = await get_db()
    user = await conn.fetchrow("SELECT * FROM users WHERE telegram_id=$1", message.from_user.id)
    await conn.close()

    if not user:
        await message.answer("Сначала зарегистрируйтесь через /start")
        return

    await message.answer(
        "Введите расписание напоминаний в формате:\n<code>mon,wed,fri 18:00</code>\n\nПримеры:\n<code>daily 09:00</code>\n<code>mon,wed,fri 18:30</code>")
    await state.set_state(Form.reminder)


@dp.message(Form.reminder)
async def process_reminder(message: Message, state: FSMContext):
    try:
        parts = message.text.split()
        days = parts[0]
        hour, minute = map(int, parts[1].split(":"))
    except:
        await message.answer("Неверный формат. Пример: <code>mon,wed,fri 18:00</code>")
        return

    await setup_user_reminders(bot, message.from_user.id, days, hour, minute)
    await message.answer("Напоминания установлены.")
    await state.clear()


# ----------------------------------------------------------
# Общее общение с ИИ
# ----------------------------------------------------------
@dp.message()
async def general_chat(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state:
        return

    if message.text.startswith("/"):
        await message.answer("Неизвестная команда. Используйте /help для списка команд")
        return

    reply = chat_with_ai(message.text)
    await message.answer(reply)


# ----------------------------------------------------------
# Запуск
# ----------------------------------------------------------
async def main():
    await init_db()
    scheduler.start()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())