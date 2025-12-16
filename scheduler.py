#scheduler.py
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz
from db import get_db
import os

TIMEZONE = pytz.timezone(os.getenv("TIMEZONE", "Europe/Moscow"))
scheduler = AsyncIOScheduler(timezone=TIMEZONE)

#Напоминание о тренировке
async def send_training_reminder(bot, user_id: int):
    await bot.send_message(
        user_id,
        "🏋️ **Тренировка сегодня!**\nНе забудьте выполнить вашу сессию. Удачи!"
    )

#Напоминание о взвешивании
async def send_weight_reminder(bot, user_id: int):
    await bot.send_message(
        user_id,
        "⚖️ Пожалуйста, введите ваш вес за сегодня."
    )

#Настройка напоминаний пользователя
async def setup_user_reminders(bot, user_id: int, days_str: str, hour: int = 18, minute: int = 0):
    """
    Настройка напоминаний о тренировках на выбранные дни и время.
    days_str: 'mon,wed,fri'
    hour, minute: время напоминания
    """
    #Удаляем старые задачи пользователя
    for job in scheduler.get_jobs():
        if str(user_id) in job.id:
            scheduler.remove_job(job.id)

    days_map = {"mon":0, "tue":1, "wed":2, "thu":3, "fri":4, "sat":5, "sun":6}

    for day in days_str.split(","):
        if day in days_map:
            # Тренировка
            scheduler.add_job(
                send_training_reminder,
                CronTrigger(day_of_week=days_map[day], hour=hour, minute=minute, timezone=TIMEZONE),
                args=[bot, user_id],
                id=f"training_{user_id}_{day}"
            )
            # Напоминание о весе
            scheduler.add_job(
                send_weight_reminder,
                CronTrigger(day_of_week=days_map[day], hour=hour-1 if hour>0 else 0, minute=minute, timezone=TIMEZONE),
                args=[bot, user_id],
                id=f"weight_{user_id}_{day}"
            )
