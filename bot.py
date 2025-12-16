import asyncio
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery, BufferedInputFile
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from datetime import datetime, timedelta
from dotenv import load_dotenv
import os

from db import init_db, get_db
from agents import generate_plan, chat_with_ai, generate_new_day_plan, analyze_progress, generate_motivation, \
    generate_daily_workout
from reports import validate_full_name, goal_map, level_map, make_excel, calculate_fitness_score
from scheduler import scheduler, setup_user_reminders

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()



# FSM
class Form(StatesGroup):
    full_name = State()
    height = State()
    weight = State()
    goal = State()
    level = State()
    update_weight = State()
    reminder = State()


# Keyboards
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


def workout_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Завершить тренировку", callback_data="finish_workout"),
        ],
        [
            InlineKeyboardButton(text="🔄 Начать новый день", callback_data="start_new_day")
        ]
    ])


# /start
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
            "/plan — посмотреть текущий план\n"
            "/workout — управление тренировками\n"
            "/setreminder — установить напоминания\n"
            "/help — справка"
        )
        return

    await message.answer(
        "Добро пожаловать в FitMind!\nВведите Фамилию Имя Отчество:"
    )
    await state.set_state(Form.full_name)


#Регистрация
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

    #Проверка на случай сбоя FSM
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

    #Генерация плана (дневной тренировки)
    plan = generate_daily_workout(user_data)

    #Сохранение
    conn = await get_db()
    try:
        await conn.execute("""
            INSERT INTO users (telegram_id, username, full_name, height, weight, goal, fitness_score, 
                              coaching_mode, current_plan, workout_streak, last_workout_date)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
            ON CONFLICT (telegram_id) DO UPDATE SET 
                full_name=$3, height=$4, weight=$5, goal=$6, current_plan=$9
        """,
                           callback.from_user.id, callback.from_user.username,
                           user_data["full_name"], user_data["height"], user_data["weight"],
                           user_data["goal"], user_data["fitness_score"], user_data["coaching_mode"],
                           plan, 0, None
                           )
    except Exception as e:
        #Если столбца нет, сохраняем без него
        await conn.execute("""
            INSERT INTO users (telegram_id, username, full_name, height, weight, goal, fitness_score, coaching_mode)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
            ON CONFLICT (telegram_id) DO UPDATE SET 
                full_name=$3, height=$4, weight=$5, goal=$6
        """,
                           callback.from_user.id, callback.from_user.username,
                           user_data["full_name"], user_data["height"], user_data["weight"],
                           user_data["goal"], user_data["fitness_score"], user_data["coaching_mode"]
                           )
    await conn.close()

    await callback.message.answer(f"🎯 <b>Ваша первая тренировка:</b>\n\n{plan}")
    await callback.message.answer("🏋️ Используйте команду /workout для управления тренировками")
    await state.clear()


# /update — обновление веса
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
    #Сохраняем вес в users
    await conn.execute("UPDATE users SET weight=$1 WHERE telegram_id=$2", weight, message.from_user.id)
    #Также сохраняем в логи прогресса
    await conn.execute("""
        INSERT INTO progress_logs (telegram_id, weight) 
        VALUES ($1, $2)
    """, message.from_user.id, weight)
    await conn.close()

    await message.answer("✅ Вес обновлён.")
    await state.clear()

#/newplan — новый план
@dp.message(Command("newplan"))
async def cmd_newplan(message: Message):
    conn = await get_db()
    user = await conn.fetchrow("SELECT * FROM users WHERE telegram_id=$1", message.from_user.id)

    if not user:
        await conn.close()
        await message.answer("Вы не зарегистрированы. Введите /start.")
        return

    user_dict = dict(user)
    plan = generate_daily_workout(user_dict)

    #Сохраняем новый план в базу
    try:
        await conn.execute("UPDATE users SET current_plan=$1 WHERE telegram_id=$2", plan, message.from_user.id)
    except Exception as e:
        # Если столбца current_plan нет, создаем его
        await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS current_plan TEXT")
        await conn.execute("UPDATE users SET current_plan=$1 WHERE telegram_id=$2", plan, message.from_user.id)
    await conn.close()

    await message.answer(f"🎯 <b>Ваш новый план:</b>\n\n{plan}")


#/plan — посмотреть текущий план

@dp.message(Command("plan"))
async def cmd_plan(message: Message):
    conn = await get_db()

    #Проверяем существование столбца current_plan
    try:
        user = await conn.fetchrow("SELECT current_plan FROM users WHERE telegram_id=$1", message.from_user.id)
    except Exception as e:
        #Если столбца нет, создаем его
        await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS current_plan TEXT")
        user = await conn.fetchrow("SELECT current_plan FROM users WHERE telegram_id=$1", message.from_user.id)

    await conn.close()

    if not user:
        await message.answer("Вы не зарегистрированы. Введите /start.")
        return

    if not user['current_plan']:
        await message.answer("У вас еще нет плана. Создайте его с помощью /newplan")
        return

    await message.answer(f"<b>Ваш текущий план:</b>\n\n{user['current_plan']}")

#/workout — управление тренировками
@dp.message(Command("workout"))
async def cmd_workout(message: Message):
    conn = await get_db()
    user = await conn.fetchrow("SELECT * FROM users WHERE telegram_id=$1", message.from_user.id)
    await conn.close()

    if not user:
        await message.answer("Сначала зарегистрируйтесь через /start")
        return

    #Получаем текущую статистику
    streak = user.get('workout_streak', 0) or 0
    last_workout = user.get('last_workout_date')

    #Проверяем статус на сегодня
    today = datetime.now().date()
    has_trained_today = False
    if last_workout:
        last_workout_date = last_workout.date() if hasattr(last_workout, 'date') else last_workout
        has_trained_today = (last_workout_date == today)

    #Создаем прогресс-бар
    progress_bar = "🟩" * min(streak, 10) + "⬜" * (10 - min(streak, 10))

    status_text = "✅ Вы уже завершили тренировку сегодня!" if has_trained_today else "🏋️ Сегодняшняя тренировка ожидает завершения"

    await message.answer(
        f"<b>Управление тренировками</b>\n\n"
        f"{status_text}\n"
        f"🔥 Серия тренировок: {streak} дней\n"
        f"{progress_bar}\n\n"
        f"<b>Доступные действия:</b>",
        reply_markup=workout_keyboard()
    )


#Завершить тренировку
@dp.callback_query(F.data == "finish_workout")
async def finish_workout(callback: CallbackQuery):
    await callback.answer()

    conn = await get_db()
    user = await conn.fetchrow("SELECT * FROM users WHERE telegram_id=$1", callback.from_user.id)

    if not user:
        await conn.close()
        await callback.message.answer("Сначала зарегистрируйтесь через /start")
        return

    #Проверяем, не завершал ли уже тренировку сегодня
    last_workout = user.get('last_workout_date')
    today = datetime.now().date()

    if last_workout:
        last_workout_date = last_workout.date() if hasattr(last_workout, 'date') else last_workout
        if last_workout_date == today:
            await conn.close()
            await callback.message.answer(
                "✅ Вы уже завершили тренировку сегодня!\n"
                "Можете начать новый день, чтобы получить новую тренировку."
            )
            return

    #Обновляем статистику
    streak = user.get('workout_streak', 0) or 0
    yesterday = (datetime.now() - timedelta(days=1)).date()

    if last_workout:
        last_workout_date = last_workout.date() if hasattr(last_workout, 'date') else last_workout
        if last_workout_date == yesterday:
            streak += 1
        elif last_workout_date < yesterday:
            streak = 1
        else:
            streak = streak  #Если тренировка была сегодня или в будущем (не должно быть)
    else:
        streak = 1

    #Увеличиваем fitness_score
    new_score = (user.get('fitness_score', 0) or 0) + 10

    await conn.execute("""
        UPDATE users 
        SET workout_streak=$1, last_workout_date=NOW(), fitness_score=$2
        WHERE telegram_id=$3
    """, streak, new_score, callback.from_user.id)

    # Сохраняем запись о тренировке
    await conn.execute("""
        INSERT INTO workout_logs (telegram_id) 
        VALUES ($1)
    """, callback.from_user.id)

    await conn.close()

    #Создаем прогресс-бар
    progress_bar = "🟩" * min(streak, 10) + "⬜" * (10 - min(streak, 10))

    await callback.message.answer(
        f"🏋️ <b>Тренировка завершена!</b>\n\n"
        f"✅ +10 очков к рейтингу\n"
        f"🔥 Серия тренировок: {streak} дней\n"
        f"{progress_bar}\n\n"
        f"🏆 Общий рейтинг: {new_score} баллов\n\n"
        f"<b>Теперь вы можете:</b>\n"
        f"1. Начать новый день для получения новой тренировки\n"
        f"2. Обновить вес с помощью /update\n"
        f"3. Посмотреть статистику через /report"
    )



# Начать новый день
@dp.callback_query(F.data == "start_new_day")
async def start_new_day(callback: CallbackQuery):
    await callback.answer()

    conn = await get_db()
    user = await conn.fetchrow("SELECT * FROM users WHERE telegram_id=$1", callback.from_user.id)

    if not user:
        await conn.close()
        await callback.message.answer("Сначала зарегистрируйтесь через /start")
        return

    #Проверяем, завершена ли сегодняшняя тренировка
    last_workout = user.get('last_workout_date')
    today = datetime.now().date()

    if not last_workout:
        await conn.close()
        await callback.message.answer(
            "⚠️ Сначала завершите свою первую тренировку!\n"
            "Используйте кнопку 'Завершить тренировку'"
        )
        return

    last_workout_date = last_workout.date() if hasattr(last_workout, 'date') else last_workout
    if last_workout_date != today:
        await conn.close()
        await callback.message.answer(
            "⚠️ Сначала завершите сегодняшнюю тренировку!\n"
            "Используйте кнопку 'Завершить тренировку'"
        )
        return

    #Получаем историю веса для анализа прогресса
    logs = await conn.fetch(
        "SELECT weight, recorded_at FROM progress_logs WHERE telegram_id=$1 ORDER BY recorded_at",
        callback.from_user.id
    )
    log_list = [(log['weight'], log['recorded_at']) for log in logs]

    #Получаем логи тренировок
    workout_logs_result = await conn.fetch(
        "SELECT workout_date FROM workout_logs WHERE telegram_id=$1 ORDER BY workout_date",
        callback.from_user.id
    )
    workout_logs = [(log['workout_date'],) for log in workout_logs_result]

    #Анализируем прогресс
    user_dict = dict(user)
    progress_analysis = analyze_progress(user_dict, log_list, workout_logs)

    #Генерируем новый план на день
    streak = user.get('workout_streak', 0) or 0
    new_plan = generate_new_day_plan(user_dict, streak, progress_analysis)

    #Сохраняем новый план
    await conn.execute("UPDATE users SET current_plan=$1 WHERE telegram_id=$2", new_plan, callback.from_user.id)

    #Генерируем мотивационное сообщение
    motivation = generate_motivation(streak, user_dict.get('goal', 'не указана'), progress_analysis)

    #Обновляем статистику (увеличиваем серию)
    streak += 1
    fitness_score = calculate_fitness_score(user_dict, log_list)

    await conn.execute("""
        UPDATE users SET workout_streak=$1, fitness_score=$2
        WHERE telegram_id=$3
    """, streak, fitness_score, callback.from_user.id)

    await conn.close()

    #Создаем прогресс-бар
    progress_bar = "🟩" * min(streak, 10) + "⬜" * (10 - min(streak, 10))

    #Отправляем два сообщения: статистику и новый план
    await callback.message.answer(
        f"🔄 <b>Новый день начат!</b>\n\n"
        f"{motivation}\n\n"
        f"📊 <b>Анализ прогресса:</b>\n"
        f"{progress_analysis}\n\n"
        f"🔥 Серия тренировок: {streak} дней подряд\n"
        f"{progress_bar}\n\n"
        f"🏆 Общий рейтинг: {fitness_score} баллов\n\n"
        f"<i>Не забывайте обновлять вес с помощью /update</i>"
    )

    #Отправляем новый план
    await callback.message.answer(
        f"🎯 <b>Ваша новая тренировка на сегодня:</b>\n\n"
        f"{new_plan}"
    )



# /report — отчёт
@dp.message(Command("report"))
async def cmd_report(message: Message):
    conn = await get_db()
    user = await conn.fetchrow("SELECT * FROM users WHERE telegram_id=$1", message.from_user.id)

    if not user:
        await conn.close()
        await message.answer("Вы не зарегистрированы. Введите /start.")
        return

    #Получаем логи прогресса
    logs = await conn.fetch(
        "SELECT weight, recorded_at FROM progress_logs WHERE telegram_id=$1 ORDER BY recorded_at",
        message.from_user.id
    )
    await conn.close()

    #Преобразуем логи в нужный формат
    log_list = [(log['weight'], log['recorded_at']) for log in logs]

    #Получаем данные пользователя в виде словаря
    user_dict = dict(user)

    #Генерируем Excel файл
    excel_file = await make_excel(user_dict, log_list)

    #Отправляем файл
    await message.answer_document(excel_file)



# /help
@dp.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "<b>Доступные команды:</b>\n\n"
        "/start — регистрация или приветствие\n"
        "/update — обновить вес\n"
        "/report — получить отчет\n"
        "/newplan — сгенерировать новый план\n"
        "/plan — посмотреть текущий план\n"
        "/workout — управление тренировками\n"
        "/setreminder — установить напоминания\n"
        "/help — справка\n\n"
        "<b>Как работать с ботом:</b>\n"
        "1. Зарегистрируйтесь через /start\n"
        "2. Выполните тренировку и отметьте её завершение\n"
        "3. Начинайте новый день для получения новой тренировки\n"
        "4. Регулярно обновляйте вес для отслеживания прогресса"
    )



# Напоминания
@dp.message(Command("setreminder"))
async def cmd_setreminder(message: Message, state: FSMContext):
    conn = await get_db()
    user = await conn.fetchrow("SELECT * FROM users WHERE telegram_id=$1", message.from_user.id)
    await conn.close()

    if not user:
        await message.answer("Сначала зарегистрируйтесь через /start")
        return

    await message.answer(
        "Введите расписание напоминаний в формате:\n<code>mon,wed,fri 18:00</code>\n\n"
        "Примеры:\n"
        "<code>daily 09:00</code> - каждый день в 9:00\n"
        "<code>mon,wed,fri 18:30</code> - по понедельникам, средам и пятницам в 18:30\n\n"
        "<b>Дни недели:</b> mon,tue,wed,thu,fri,sat,sun"
    )
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
    await message.answer("✅ Напоминания установлены.")
    await state.clear()



# Общее общение с ИИ
@dp.message()
async def general_chat(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state:
        return

    if message.text.startswith("/"):
        await message.answer("Неизвестная команда. Используйте /help для списка команд")
        return

    # Получаем контекст пользователя для улучшенного ответа
    conn = await get_db()
    user = await conn.fetchrow("SELECT goal, workout_streak FROM users WHERE telegram_id=$1", message.from_user.id)
    await conn.close()

    context = {}
    if user:
        context = {
            'goal': user['goal'],
            'streak': user.get('workout_streak', 0) or 0
        }

    reply = chat_with_ai(message.text, context)
    await message.answer(reply)



# Миграция базы данных при запуске
async def migrate_db():
    """Добавляем недостающие столбцы и таблицы если они не существуют"""
    conn = await get_db()
    try:
        # Проверяем существование столбца current_plan
        await conn.fetch("SELECT current_plan FROM users LIMIT 1")
    except Exception as e:
        if "столбец" in str(e).lower() and "не существует" in str(e).lower():
            await conn.execute("ALTER TABLE users ADD COLUMN current_plan TEXT")

    try:
        await conn.fetch("SELECT workout_streak FROM users LIMIT 1")
    except Exception as e:
        if "столбец" in str(e).lower() and "не существует" in str(e).lower():
            await conn.execute("ALTER TABLE users ADD COLUMN workout_streak INTEGER DEFAULT 0")

    try:
        await conn.fetch("SELECT last_workout_date FROM users LIMIT 1")
    except Exception as e:
        if "столбец" in str(e).lower() and "не существует" in str(e).lower():
            await conn.execute("ALTER TABLE users ADD COLUMN last_workout_date TIMESTAMP")

    # Создаем таблицу для логов тренировок
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS workout_logs (
            id SERIAL PRIMARY KEY,
            telegram_id BIGINT REFERENCES users(telegram_id) ON DELETE CASCADE,
            workout_date TIMESTAMP DEFAULT NOW()
        )
    """)

    await conn.close()



# Запуск
async def main():
    await init_db()
    await migrate_db()  # Выполняем миграцию
    scheduler.start()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())