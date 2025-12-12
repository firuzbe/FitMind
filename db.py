# db.py
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

async def get_db():
    return await asyncpg.connect(os.getenv("DATABASE_URL"))

async def init_db():
    conn = await get_db()
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            telegram_id BIGINT PRIMARY KEY,
            username TEXT,
            full_name TEXT NOT NULL,
            height INT NOT NULL,
            weight REAL NOT NULL,
            goal TEXT NOT NULL,
            fitness_score INT DEFAULT 0,
            coaching_mode TEXT DEFAULT 'level1',
            registered_at TIMESTAMP DEFAULT NOW(),
            level_entered_at TIMESTAMP DEFAULT NOW(),
            last_export TIMESTAMP,
            next_reminder_days TEXT DEFAULT 'mon,wed,fri'
        );
        CREATE TABLE IF NOT EXISTS progress_logs (
            id SERIAL PRIMARY KEY,
            telegram_id BIGINT REFERENCES users(telegram_id) ON DELETE CASCADE,
            weight REAL NOT NULL,
            recorded_at TIMESTAMP DEFAULT NOW()
        );
    """)
    await conn.close()