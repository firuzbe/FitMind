from langchain_core.messages import SystemMessage, HumanMessage
from langchain_groq import ChatGroq
import os
from dotenv import load_dotenv

load_dotenv()

llm = ChatGroq(
    api_key=os.getenv("GROQ_API_KEY"),
    model="llama-3.1-8b-instant",
    temperature=0.5,
    max_tokens=800,
)

SYSTEM_PROMPT = (
    "Ты — сертифицированный профессиональный фитнес-тренер с 10-летним опытом. "
    "Ты даёшь точные, безопасные, персонализированные рекомендации. "
    "Никогда не используй эмодзи, восклицания, разговорные фразы, панибратство или вступления. "
    "Говори только по делу, на русском языке, в чёткой структуре. "
    "Всегда добавляй: «Перед началом программы проконсультируйтесь с врачом, если есть хронические заболевания»."
)

# -------------------- Вызов LLM --------------------
def _invoke_llm(messages: list, use_system_prompt: bool = True):
    if use_system_prompt:
        messages.insert(0, SystemMessage(content=SYSTEM_PROMPT))
    response = llm.invoke(messages)
    return response.content

# -------------------- Генерация плана --------------------
def generate_plan(user_data: dict) -> str:
    mode = user_data.get("coaching_mode", "level1")
    goal = user_data["goal"]
    height = user_data["height"]
    weight = user_data["weight"]

    if mode == "level3":
        prompt = f"Пользователь: {height} см, {weight} кг, цель: {goal}. Уровень: Продвинутый.\nСоздай годовой фитнес-план с фазами, БЖУ, прогрессией, восстановлением."
    elif mode == "level2":
        prompt = f"Пользователь: {height} см, {weight} кг, цель: {goal}. Уровень: Средний.\nСоздай месячный план с прогрессией по неделям."
    else:
        prompt = f"Пользователь: {height} см, {weight} кг, цель: {goal}. Уровень: Новичок.\nСоздай недельный план с 3 тренировками и питанием."

    messages = [HumanMessage(content=prompt)]
    return _invoke_llm(messages, use_system_prompt=True)

# -------------------- Анализ прогресса --------------------
def analyze_progress(user_data: dict, progress: list) -> str:
    if not progress:
        return "Недостаточно данных для анализа."
    init, curr = progress[0][0], progress[-1][0]
    goal = user_data["goal"]
    diff = curr - init
    if goal == "похудение":
        trend = "вес снижается" if diff < -0.5 else "вес не снижается"
    elif goal == "набор мышечной массы":
        trend = "вес растёт" if diff > 0.5 else "вес не растёт"
    else:
        trend = "вес стабилен" if abs(diff) <= 1.0 else "вес колеблется"

    prompt = f"Начальный вес: {init}, текущий: {curr}, цель: {goal}, наблюдается: {trend}. Дай комментарий и рекомендацию."
    messages = [HumanMessage(content=prompt)]
    return _invoke_llm(messages, use_system_prompt=True)

# -------------------- Обычный чат с ИИ --------------------
def chat_with_ai(user_message: str) -> str:
    """
    Общение с пользователем без системного фитнес-промта.
    """
    messages = [HumanMessage(content=user_message)]
    return _invoke_llm(messages, use_system_prompt=False)
