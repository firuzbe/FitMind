from langchain_core.messages import SystemMessage, HumanMessage
from langchain_groq import ChatGroq
import os
from dotenv import load_dotenv

load_dotenv()

llm = ChatGroq(
    api_key=os.getenv("GROQ_API_KEY"),
    model="llama-3.1-8b-instant",
    temperature=0.5,
    max_tokens=1000,  # Увеличил для более детальных планов
)

SYSTEM_PROMPT = (
    "Ты — сертифицированный профессиональный фитнес-тренер с 10-летним опытом. "
    "Ты даёшь точные, безопасные, персонализированные рекомендации. "
    "Никогда не используй эмодзи, восклицания, разговорные фразы, панибратство или вступления. "
    "Говори только по делу, на русском языке, в чёткой структуре. "
    "Всегда добавляй: «Перед началом программы проконсультируйтесь с врачом, если есть хронические заболевания»."
)

FITNESS_LEVELS = {
    "level1": "новичок",
    "level2": "средний уровень",
    "level3": "продвинутый"
}


# Вызов LLM
def _invoke_llm(messages: list, use_system_prompt: bool = True):
    if use_system_prompt:
        messages.insert(0, SystemMessage(content=SYSTEM_PROMPT))
    response = llm.invoke(messages)
    return response.content


# Генерация дневной тренировки
def generate_daily_workout(user_data: dict) -> str:
    """
    Генерирует одну часовую тренировку на день.
    Объединяет упражнения на разные группы мышц в одну сессию.
    """
    goal = user_data["goal"]
    height = user_data["height"]
    weight = user_data["weight"]
    level = user_data.get("level", "новичок")
    coaching_mode = user_data.get("coaching_mode", "level1")

    # Определяем фокус тренировки в зависимости от цели
    workout_focus = {
        "похудение": "с упором на сжигание калорий и кардио-упражнения",
        "набор мышечной массы": "с акцентом на силовые упражнения и рост мышц",
        "поддержание формы": "сбалансированная тренировка для тонуса и здоровья"
    }.get(goal, "универсальная тренировка")

    prompt = f"""Пользователь: {height} см, {weight} кг, цель: {goal}. Уровень подготовки: {level}.

Создай ОДНУ часовую тренировку (60 минут) для пользователя. Тренировка должна быть {workout_focus}.

**Структура тренировки:**
1. Разминка (5-10 минут) - динамическая растяжка, легкий кардио
2. Основная часть (40-45 минут) - комплекс упражнений
3. Заминка (5-10 минут) - статическая растяжка, восстановление

**Требования к основной части:**
- 6-8 упражнений на разные группы мышц
- Каждое упражнение: 3 подхода по 10-15 повторений (или 30-60 секунд для планки/кардио)
- Отдых между подходами: 60-90 секунд
- Включи упражнения на: грудь, спину, ноги, пресс
- Добавь 1-2 кардио-упражнения если цель - похудение

**Формат ответа:**
Название тренировки

**Разминка:**
- Упражнение 1
- Упражнение 2

**Основная часть:**
1. Упражнение (группа мышц) - 3x10-15
2. Упражнение (группа мышц) - 3x10-15
...

**Заминка:**
- Упражнение 1
- Упражнение 2

**Рекомендации по питанию на день:**
- Белки: ...
- Углеводы: ...
- Жиры: ...
- Калории: ...
- Пример приемов пищи

Перед началом программы проконсультируйтесь с врачом, если есть хронические заболевания."""

    messages = [HumanMessage(content=prompt)]
    return _invoke_llm(messages, use_system_prompt=True)


#Генерация плана старая версия - оставляем для обратной совместимости
def generate_plan(user_data: dict) -> str:
    """
    Основная функция генерации плана.
    Для новичков генерирует дневную тренировку, для других уровней - более сложные планы.
    """
    coaching_mode = user_data.get("coaching_mode", "level1")
    goal = user_data["goal"]
    height = user_data["height"]
    weight = user_data["weight"]
    level = user_data.get("level", "новичок")

    if coaching_mode == "level3":
        prompt = f"""Пользователь: {height} см, {weight} кг, цель: {goal}. Уровень: Продвинутый.

Создай продвинутый фитнес-план. Включи:
1. Тренировочный сплит на неделю
2. Прогрессию нагрузок
3. Периодизацию
4. Рекомендации по восстановлению
5. Детальное питание с БЖУ"""

    elif coaching_mode == "level2":
        prompt = f"""Пользователь: {height} см, {weight} кг, цель: {goal}. Уровень: Средний.

Создай месячный план тренировок. Включи:
1. 4 тренировки в неделю
2. Прогрессию по неделям
3. Упражнения с весами
4. Базовые рекомендации по питанию"""

    else:  # level1 - новичок
        # Используем новую функцию для генерации дневной тренировки
        return generate_daily_workout(user_data)

    messages = [HumanMessage(content=prompt)]
    return _invoke_llm(messages, use_system_prompt=True)


#Генерация нового плана на день
def generate_new_day_plan(user_data: dict, streak: int, previous_progress: str = "") -> str:
    """
    Генерирует новый план на день с учетом прогресса и серии тренировок.
    """
    goal = user_data["goal"]
    height = user_data["height"]
    weight = user_data["weight"]
    level = user_data.get("level", "новичок")

    #Адаптируем тренировку в зависимости от серии
    intensity_modifier = ""
    if streak >= 7:
        intensity_modifier = "Увеличь интенсивность на 10-15% по сравнению с предыдущими днями."
    elif streak >= 3:
        intensity_modifier = "Сохрани текущую интенсивность, можно немного увеличить веса."
    else:
        intensity_modifier = "Сфокусируйся на правильной технике, не гонись за весами."

    prompt = f"""Пользователь: {height} см, {weight} кг, цель: {goal}. Уровень: {level}.
Серия тренировок: {streak} дней подряд.

{intensity_modifier}

{previous_progress if previous_progress else "Пользователь только начинает свой путь."}

Создай новую часовую тренировку на сегодня. Вариативность важна - не повторяй одни и те же упражнения каждый день.

**Требования:**
1. Новая тренировка с разными упражнениями или их вариациями
2. Учет серии тренировок: {streak} дней
3. Фокус на цели: {goal}
4. Полная продолжительность: 60 минут

**Структура:**
- Разминка (5-10 мин)
- Основная часть (40-45 мин) - 6-8 упражнений
- Заминка (5-10 мин)

**Особое внимание:**
1. Если цель - похудение: добавь больше кардио-элементов
2. Если цель - набор массы: акцент на базовые упражнения
3. Если цель - поддержание формы: сбалансированный подход

Перед началом программы проконсультируйтесь с врачом, если есть хронические заболевания."""

    messages = [HumanMessage(content=prompt)]
    return _invoke_llm(messages, use_system_prompt=True)


# Анализ прогресса
def analyze_progress(user_data: dict, progress: list, workout_logs: list = None) -> str:
    """
    Анализирует прогресс пользователя и дает рекомендации.
    """
    if not progress:
        return "Пока недостаточно данных для анализа. Продолжайте тренировки и обновляйте вес регулярно!"

    # Анализ веса
    init_weight = progress[0][0]
    current_weight = progress[-1][0]
    goal = user_data["goal"]
    diff = current_weight - init_weight

    # Анализ тренировок
    workout_count = len(workout_logs) if workout_logs else 0
    if workout_logs and len(workout_logs) > 1:
        first_date = min(log[1] for log in workout_logs)
        last_date = max(log[1] for log in workout_logs)
        days_active = (last_date - first_date).days + 1
        consistency = workout_count / max(days_active, 1)
    else:
        consistency = 0

    # Генерация анализа
    if goal == "похудение":
        if diff < -1.5:
            analysis = f"Отличный прогресс! Вы похудели на {abs(diff):.1f} кг."
            recommendation = "Продолжайте текущий режим. Можете немного увеличить кардио-нагрузку."
        elif diff < -0.5:
            analysis = f"Хороший результат! Потеря веса: {abs(diff):.1f} кг."
            recommendation = "Увеличьте интенсивность тренировок на 10%."
        elif diff <= 0:
            analysis = "Вес стабилизировался."
            recommendation = "Пересмотрите питание и добавьте интервальные тренировки."
        else:
            analysis = f"Вес увеличился на {diff:.1f} кг."
            recommendation = "Срочно пересмотрите калорийность питания и увеличьте кардио."

    elif goal == "набор мышечной массы":
        if diff > 1.5:
            analysis = f"Отличный результат! Набор веса: {diff:.1f} кг."
            recommendation = "Скорее всего, это мышечная масса. Продолжайте силовые тренировки."
        elif diff > 0.5:
            analysis = f"Хороший прогресс! Набор: {diff:.1f} кг."
            recommendation = "Увеличьте потребление белка до 2г на кг веса."
        elif diff >= 0:
            analysis = "Вес стабилен."
            recommendation = "Увеличьте калорийность на 200-300 ккал в день."
        else:
            analysis = f"Потеря веса: {abs(diff):.1f} кг."
            recommendation = "Срочно увеличьте калорийность и потребление белка."

    else:  # поддержание формы
        if abs(diff) <= 1:
            analysis = "Отлично! Вы успешно поддерживаете форму."
            recommendation = "Продолжайте текущий режим тренировок и питания."
        elif abs(diff) <= 2:
            analysis = f"Небольшое изменение веса: {diff:.1f} кг."
            recommendation = "Скорректируйте питание на 100-200 ккал."
        else:
            analysis = f"Значительное изменение веса: {diff:.1f} кг."
            recommendation = "Пересмотрите полностью свой режим тренировок и питания."

    # Добавляем анализ консистенции тренировок
    if workout_count > 0:
        if consistency >= 0.8:
            consistency_text = "Вы тренируетесь очень регулярно! Это отличная привычка."
        elif consistency >= 0.5:
            consistency_text = "Хорошая регулярность тренировок. Можно улучшить."
        else:
            consistency_text = "Регулярность тренировок низкая. Старайтесь заниматься чаще."

        analysis += f"\n\nТренировок выполнено: {workout_count}. {consistency_text}"

    # Генерация финального промпта для ИИ
    prompt = f"""Начальный вес: {init_weight} кг
Текущий вес: {current_weight} кг
Изменение: {diff:.1f} кг
Цель: {goal}
Анализ: {analysis}
Рекомендация: {recommendation}

Дайте развернутый комментарий и конкретные рекомендации на следующие 7 дней."""

    messages = [HumanMessage(content=prompt)]
    return _invoke_llm(messages, use_system_prompt=True)


#Обычный чат с ИИ
def chat_with_ai(user_message: str, context: dict = None) -> str:
    """
    Общение с пользователем с возможностью контекста.
    """
    messages = [HumanMessage(content=user_message)]

    # Если есть контекст, добавляем его
    if context:
        context_message = f"Контекст: Пользователь тренируется {context.get('streak', 0)} дней, цель: {context.get('goal', 'не указана')}."
        messages.insert(0, HumanMessage(content=context_message))

    return _invoke_llm(messages, use_system_prompt=False)


#Генерация мотивационного сообщения
def generate_motivation(streak: int, goal: str, recent_progress: str = "") -> str:
    """
    Генерирует мотивационное сообщение на основе серии тренировок.
    """
    if streak >= 21:
        level = "Эксперт"
        motivation = "Вы выработали устойчивую привычку! Теперь фитнес - часть вашей жизни."
    elif streak >= 14:
        level = "Продвинутый"
        motivation = "Две недели подряд - это серьезное достижение! Тело начало адаптироваться."
    elif streak >= 7:
        level = "Регулярный"
        motivation = "Неделя регулярных тренировок - отличный результат! Вы на правильном пути."
    elif streak >= 3:
        level = "Начинающий"
        motivation = "Хорошее начало! Первые дни самые важные для формирования привычки."
    else:
        level = "Новичок"
        motivation = "Каждое начало трудно, но вы сделали первый шаг! Продолжайте в том же духе."

    prompt = f"""Пользователь тренируется {streak} дней подряд. Уровень: {level}. Цель: {goal}.

{recent_progress if recent_progress else ""}

Сгенерируйте короткое мотивационное сообщение (2-3 предложения) для поддержки пользователя.
Сообщение должно быть энергичным, но без эмодзи и восклицаний."""

    messages = [HumanMessage(content=prompt)]
    return _invoke_llm(messages, use_system_prompt=True)